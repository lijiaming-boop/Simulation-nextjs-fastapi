package main

import (
	"fmt"
	"net/http"
	"os"

	"github.com/gin-gonic/gin"
	"github.com/joho/godotenv"

	"oauth-server/internal/handler"
	"oauth-server/internal/service"
	"oauth-server/internal/store"
	"oauth-server/internal/token"
)

var (
	serverPort   string
	issuer       string
	enableCORS   bool
	allowedOrigins []string
)

func init() {
	// 加载 .env 文件
	godotenv.Load()

	// 从环境变量读取配置
	serverPort = getEnv("SERVER_PORT", "8081")
	issuer = getEnv("ISSUER", "http://localhost:"+serverPort)
	enableCORS = getEnv("ENABLE_CORS", "false") == "true"
	
	// 解析允许的源
	originsStr := getEnv("ALLOWED_ORIGINS", "")
	if originsStr != "" {
		// 简单的逗号分隔解析
		for _, origin := range splitString(originsStr, ",") {
			allowedOrigins = append(allowedOrigins, trimSpace(origin))
		}
	}
}

func main() {
	// 初始化 Gin
	r := gin.Default()

	// 加载 HTML 模板
	r.LoadHTMLGlob("templates/*")

	// CORS 中间件（可选）
	if enableCORS && len(allowedOrigins) > 0 {
		r.Use(corsMiddleware())
	}

	// 初始化组件
	tokenManager, err := token.NewTokenManager()
	if err != nil {
		panic(fmt.Sprintf("Failed to create token manager: %v", err))
	}

	// 初始化存储（优先使用 MySQL，失败则回退到内存存储）
	var mysqlStore store.Store
	mysqlStore, err = store.NewMySQLStore()
	if err != nil {
		fmt.Printf("Warning: Failed to create MySQL store: %v\n", err)
		fmt.Println("Falling back to MemoryStore for demonstration...")
		mysqlStore = store.NewMemoryStore()
	}
	defer func() {
		if ms, ok := mysqlStore.(*store.MySQLStore); ok {
			ms.Close()
		}
	}()

	oauthService := service.NewOAuthService(mysqlStore, tokenManager, issuer)
	oauthHandler := handler.NewOAuthHandler(oauthService, tokenManager, mysqlStore, issuer)

	// 健康检查
	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"status": "ok",
			"issuer": issuer,
		})
	})

	// OAuth 2.0 / OIDC 端点
	r.GET("/oauth/authorize", oauthHandler.Authorize)
	r.POST("/oauth/login", oauthHandler.HandleLogin)
	r.POST("/oauth/quick-login", oauthHandler.HandleQuickLogin)
	r.POST("/oauth/token", oauthHandler.Token)
	r.GET("/oauth/userinfo", oauthHandler.UserInfo)
	r.POST("/oauth/introspect", oauthHandler.Introspect)

	// OIDC 发现端点
	r.GET("/.well-known/openid-configuration", oauthHandler.WellKnownOIDC)
	r.GET("/.well-known/jwks.json", oauthHandler.JWKS)

	// 首页
	r.GET("/", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"name":        "OAuth 2.0 Server",
			"description": "Conditioner Saving OAuth 2.0 Authorization Server",
			"issuer":      issuer,
			"endpoints": gin.H{
				"authorization":              "/oauth/authorize",
				"token":                      "/oauth/token",
				"userinfo":                   "/oauth/userinfo",
				"introspect":                 "/oauth/introspect",
				"jwks":                       "/.well-known/jwks.json",
				"openid-configuration":       "/.well-known/openid-configuration",
			},
			"supported_grant_types": []string{
				"authorization_code",
				"refresh_token",
				"client_credentials",
			},
		})
	})

	// 启动服务器
	fmt.Println("===========================================")
	fmt.Println("  OAuth 2.0 Authorization Server")
	fmt.Println("===========================================")
	fmt.Printf("  Issuer: %s\n", issuer)
	fmt.Printf("  Port: %s\n", serverPort)
	fmt.Printf("  CORS: %v\n", enableCORS)
	if len(allowedOrigins) > 0 {
		fmt.Printf("  Allowed Origins: %v\n", allowedOrigins)
	}
	fmt.Println("===========================================")
	fmt.Println("  OAuth 2.0 Endpoints:")
	fmt.Println("    GET  /oauth/authorize          - 授权端点")
	fmt.Println("    POST /oauth/login              - 登录处理")
	fmt.Println("    POST /oauth/token              - Token 端点")
	fmt.Println("    GET  /oauth/userinfo           - 用户信息")
	fmt.Println("    POST /oauth/introspect         - Token 验证")
	fmt.Println("    GET  /.well-known/jwks.json    - JWKS 端点")
	fmt.Println("    GET  /.well-known/openid-configuration - OIDC 发现")
	fmt.Println("===========================================")
	fmt.Printf("  Server starting on http://localhost:%s\n", serverPort)
	fmt.Println("===========================================")

	if err := r.Run(":" + serverPort); err != nil {
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

// splitString 分割字符串
func splitString(s, sep string) []string {
	var result []string
	start := 0
	for i := 0; i <= len(s)-len(sep); i++ {
		if s[i:i+len(sep)] == sep {
			result = append(result, s[start:i])
			start = i + len(sep)
			i = start - 1
		}
	}
	result = append(result, s[start:])
	return result
}

// trimSpace 去除空格
func trimSpace(s string) string {
	result := ""
	for _, r := range s {
		if r != ' ' && r != '\t' {
			result += string(r)
		}
	}
	return result
}

// corsMiddleware CORS 中间件
func corsMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		origin := c.GetHeader("Origin")
		
		// 检查是否在允许的源列表中
		allowed := false
		for _, o := range allowedOrigins {
			if o == "*" || o == origin {
				allowed = true
				break
			}
		}

		if allowed {
			c.Header("Access-Control-Allow-Origin", origin)
			c.Header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
			c.Header("Access-Control-Allow-Headers", "Origin, Content-Type, Authorization")
			c.Header("Access-Control-Allow-Credentials", "true")
		}

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}

		c.Next()
	}
}
