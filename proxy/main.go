package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/coreos/go-oidc/v3/oidc"
	"github.com/gin-gonic/gin"
	"github.com/joho/godotenv"
	"golang.org/x/oauth2"
)

// Casdoor 配置
var (
	casdoorServerURL   string
	clientID           string
	clientSecret       string
	redirectURI        string
	streamlitBackend   string
	cookieSecret       []byte
	sessionCookieName  string
	userInfoCookieName string
	proxyPort          string
)

// OAuth2 配置
var (
	oauth2Config *oauth2.Config
	provider     *oidc.Provider
	verifier     *oidc.IDTokenVerifier
)

// UserInfo 用户信息结构
type UserInfo struct {
	Sub       string `json:"sub"`
	Name      string `json:"name"`
	Email     string `json:"email"`
	Avatar    string `json:"avatar"`
	LoginName string `json:"loginName"`
}

func init() {
	// 加载 .env 文件（仅开发环境）
	godotenv.Load()

	// 从环境变量读取配置
	casdoorServerURL = getEnv("CASDOOR_SERVER_URL", "https://casdoor.mogulinker.com")
	clientID = getEnv("CLIENT_ID", "")
	clientSecret = getEnv("CLIENT_SECRET", "")
	redirectURI = getEnv("REDIRECT_URI", "http://localhost:8080/oauth2callback")
	streamlitBackend = getEnv("STREAMLIT_BACKEND", "http://localhost:8501")
	cookieSecret = []byte(getEnv("COOKIE_SECRET", "change-this-secret-in-production"))
	sessionCookieName = getEnv("SESSION_COOKIE_NAME", "session_token")
	userInfoCookieName = getEnv("USER_INFO_COOKIE_NAME", "user_info")
	proxyPort = getEnv("PROXY_PORT", "8080")

	// 初始化 OIDC Provider
	ctx := context.Background()
	var err error
	provider, err = oidc.NewProvider(ctx, casdoorServerURL)
	if err != nil {
		panic(fmt.Sprintf("Failed to initialize OIDC provider: %v", err))
	}

	// 配置 OAuth2
	oauth2Config = &oauth2.Config{
		ClientID:     clientID,
		ClientSecret: clientSecret,
		RedirectURL:  redirectURI,
		Scopes:       []string{oidc.ScopeOpenID, "email", "profile"},
		Endpoint:     provider.Endpoint(),
	}

	// 配置 ID Token 验证器
	verifier = provider.Verifier(&oidc.Config{
		ClientID: clientID,
	})
}

func main() {
	r := gin.Default()

	// 静态文件和健康检查
	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	// OAuth2 回调处理
	r.GET("/oauth2callback", handleCallback)

	// 登录路由
	r.GET("/login", handleLogin)

	// 登出路由
	r.GET("/logout", handleLogout)

	// 认证中间件
	authMiddleware := AuthMiddleware()

	// 反向代理到 Streamlit - 所有其他请求
	r.NoRoute(authMiddleware, proxyToStreamlit())

	// 启动服务
	fmt.Println("===========================================")
	fmt.Println("  Conditioner Saving Proxy Server")
	fmt.Println("===========================================")
	fmt.Printf("  Casdoor Server: %s\n", casdoorServerURL)
	fmt.Printf("  Streamlit Backend: %s\n", streamlitBackend)
	fmt.Printf("  Redirect URI: %s\n", redirectURI)
	fmt.Printf("  Port: %s\n", proxyPort)
	fmt.Println("===========================================")
	fmt.Printf("  Server starting on http://localhost:%s\n", proxyPort)
	fmt.Println("===========================================")

	if err := r.Run(":" + proxyPort); err != nil {
		panic(fmt.Sprintf("Failed to start server: %v", err))
	}
}

// getEnv 获取环境变量，如果不存在则返回默认值
func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

// handleLogin 处理登录请求
func handleLogin(c *gin.Context) {
	state := generateRandomString()
	c.SetCookie("oauth_state", state, 300, "/", "", false, true)

	nonce := generateRandomString()
	c.SetCookie("oauth_nonce", nonce, 300, "/", "", false, true)

	authURL := oauth2Config.AuthCodeURL(state, oidc.Nonce(nonce))
	c.Redirect(http.StatusTemporaryRedirect, authURL)
}

// handleCallback 处理 OAuth 回调
func handleCallback(c *gin.Context) {
	state := c.Query("state")
	code := c.Query("code")

	// 验证 state
	savedState, err := c.Cookie("oauth_state")
	if err != nil || state != savedState {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid state"})
		return
	}

	// 获取 nonce
	savedNonce, _ := c.Cookie("oauth_nonce")

	ctx := context.Background()

	// 交换 token
	token, err := oauth2Config.Exchange(ctx, code)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to exchange token: %v", err)})
		return
	}

	// 验证并提取 ID Token
	rawIDToken, ok := token.Extra("id_token").(string)
	if !ok {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "no id_token in token response"})
		return
	}

	idToken, err := verifier.Verify(ctx, rawIDToken)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to verify id_token: %v", err)})
		return
	}

	// 验证 nonce
	if idToken.Nonce != savedNonce {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "invalid nonce"})
		return
	}

	// 获取用户信息
	var userInfo UserInfo
	if err := idToken.Claims(&userInfo); err != nil {
		// 如果 ID Token 中没有用户信息，尝试从 userinfo endpoint 获取
		userInfoEndpoint := casdoorServerURL + "/api/userinfo"
		resp, err := oauth2Config.Client(ctx, token).Get(userInfoEndpoint)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to get userinfo: %v", err)})
			return
		}
		defer resp.Body.Close()
		if err := json.NewDecoder(resp.Body).Decode(&userInfo); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to decode userinfo: %v", err)})
			return
		}
	}

	// 生成会话 token（使用 access token 作为会话标识）
	sessionToken := token.AccessToken

	// 设置会话 cookie（不设置过期时间，浏览器关闭自动清除）
	c.SetCookie(sessionCookieName, sessionToken, 0, "/", "", false, true)

	// 设置用户信息 cookie（不设置过期时间，浏览器关闭自动清除）
	userInfoJSON, _ := json.Marshal(userInfo)
	c.SetCookie(userInfoCookieName, string(userInfoJSON), 0, "/", "", false, false)

	// 重定向到应用首页
	c.Redirect(http.StatusTemporaryRedirect, "/")
}

// handleLogout 处理登出请求
func handleLogout(c *gin.Context) {
	c.SetCookie(sessionCookieName, "", -1, "/", "", false, true)
	c.SetCookie(userInfoCookieName, "", -1, "/", "", false, false)

	// 重定向到登录页
	c.Redirect(http.StatusTemporaryRedirect, "/")
}

// AuthMiddleware 认证中间件
func AuthMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		// 排除 OAuth 回调和登录路由
		if strings.HasPrefix(c.Request.URL.Path, "/oauth2callback") ||
			strings.HasPrefix(c.Request.URL.Path, "/login") ||
			strings.HasPrefix(c.Request.URL.Path, "/health") {
			c.Next()
			return
		}

		// 检查会话 cookie
		sessionToken, err := c.Cookie(sessionCookieName)
		if err != nil || sessionToken == "" {
			// 未登录，重定向到登录页
			c.Redirect(http.StatusTemporaryRedirect, "/login")
			c.Abort()
			return
		}

		// 获取并解析用户信息
		userInfoJSON, err := c.Cookie(userInfoCookieName)
		if err != nil {
			// 用户信息不存在，清除会话
			c.SetCookie(sessionCookieName, "", -1, "/", "", false, true)
			c.Redirect(http.StatusTemporaryRedirect, "/login")
			c.Abort()
			return
		}

		var userInfo UserInfo
		if err := json.Unmarshal([]byte(userInfoJSON), &userInfo); err != nil {
			// 解析失败，清除会话
			c.SetCookie(sessionCookieName, "", -1, "/", "", false, true)
			c.SetCookie(userInfoCookieName, "", -1, "/", "", false, false)
			c.Redirect(http.StatusTemporaryRedirect, "/login")
			c.Abort()
			return
		}

		// 将用户信息存入上下文
		c.Set("user_info", userInfo)
		c.Set("session_token", sessionToken)

		c.Next()
	}
}

// proxyToStreamlit 反向代理到 Streamlit
func proxyToStreamlit() gin.HandlerFunc {
	remote, err := url.Parse(streamlitBackend)
	if err != nil {
		panic(fmt.Sprintf("Failed to parse streamlit backend URL: %v", err))
	}

	proxy := httputil.NewSingleHostReverseProxy(remote)
	originalDirector := proxy.Director
	proxy.Director = func(req *http.Request) {
		originalDirector(req)
		req.Host = remote.Host
		req.Header.Set("X-Forwarded-Host", req.Host)
		req.Header.Set("X-Forwarded-Proto", "http")

		// 从上下文添加用户信息到请求头
		if userInfo, exists := getuserInfoFromContext(req); exists {
			userInfoJSON, _ := json.Marshal(userInfo)
			req.Header.Set("X-User-Info", string(userInfoJSON))
		}
	}

	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		fmt.Printf("Proxy error: %v\n", err)
		w.WriteHeader(http.StatusBadGateway)
		w.Write([]byte(fmt.Sprintf("Streamlit backend error: %v", err)))
	}

	return func(c *gin.Context) {
		proxy.ServeHTTP(c.Writer, c.Request)
	}
}

// getuserInfoFromContext 从请求中获取用户信息（通过 cookie）
func getuserInfoFromContext(r *http.Request) (UserInfo, bool) {
	cookie, err := r.Cookie(userInfoCookieName)
	if err != nil {
		return UserInfo{}, false
	}

	var userInfo UserInfo
	if err := json.Unmarshal([]byte(cookie.Value), &userInfo); err != nil {
		return UserInfo{}, false
	}

	return userInfo, true
}

// generateRandomString 生成随机字符串
func generateRandomString() string {
	b := make([]byte, 32)
	for i := range b {
		b[i] = byte(time.Now().UnixNano() >> (i * 8) & 0xFF)
	}
	return fmt.Sprintf("%x", b)[:32]
}
