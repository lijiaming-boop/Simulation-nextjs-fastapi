package handler

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"

	"oauth-server/internal/models"
	"oauth-server/internal/service"
	"oauth-server/internal/store"
	"oauth-server/internal/token"
)

// OAuthHandler OAuth 处理器
type OAuthHandler struct {
	service      *service.OAuthService
	tokenManager *token.TokenManager
	store        store.Store
	issuer       string
}

// NewOAuthHandler 创建新的 OAuth 处理器
func NewOAuthHandler(
	service *service.OAuthService,
	tokenManager *token.TokenManager,
	store store.Store,
	issuer string,
) *OAuthHandler {
	return &OAuthHandler{
		service:      service,
		tokenManager: tokenManager,
		store:        store,
		issuer:       issuer,
	}
}

// Authorize 授权端点 (GET /oauth/authorize)
func (h *OAuthHandler) Authorize(c *gin.Context) {
	var req models.AuthRequest
	if err := c.ShouldBindQuery(&req); err != nil {
		h.renderError(c, http.StatusBadRequest, "invalid_request", err.Error())
		return
	}

	// 验证 response_type
	if req.ResponseType != "code" {
		h.renderError(c, http.StatusBadRequest, "unsupported_response_type", "Only authorization_code is supported")
		return
	}

	// 验证客户端
	client, exists := h.store.GetClient(req.ClientID)
	if !exists {
		h.renderError(c, http.StatusBadRequest, "invalid_client", "Client not found")
		return
	}

	// 验证 redirect_uri
	if req.RedirectURI != "" {
		validURI := false
		for _, uri := range client.RedirectURIs {
			if uri == req.RedirectURI {
				validURI = true
				break
			}
		}
		if !validURI {
			h.renderError(c, http.StatusBadRequest, "redirect_uri_mismatch", "Redirect URI not registered")
			return
		}
	}

	h.showLoginPage(c, &req)
}

func (h *OAuthHandler) showLoginPage(c *gin.Context, req *models.AuthRequest) {
	// 获取客户端信息
	client, _ := h.store.GetClient(req.ClientID)
	clientName := ""
	if client != nil {
		clientName = client.Name
	}

	c.HTML(http.StatusOK, "login.html", gin.H{
		"ClientID":     req.ClientID,
		"ClientName":   clientName,
		"RedirectURI":  req.RedirectURI,
		"ResponseType": req.ResponseType,
		"Scope":        req.Scope,
		"State":        req.State,
		"Nonce":        req.Nonce,
	})
}

// HandleLogin 处理登录请求 (POST /oauth/login)
func (h *OAuthHandler) HandleLogin(c *gin.Context) {
	clientID := c.PostForm("client_id")
	redirectURI := c.PostForm("redirect_uri")
	responseType := c.PostForm("response_type")
	scope := c.PostForm("scope")
	state := c.PostForm("state")
	nonce := c.PostForm("nonce")
	username := c.PostForm("username")
	password := c.PostForm("password")

	// 验证用户名和密码
	if username == "" || password == "" {
		h.renderError(c, http.StatusBadRequest, "invalid_request", "Username and password are required")
		return
	}

	// 通过 MySQL 验证用户
	userInfo, err := h.store.GetUserByCredentials(username, password)
	if err != nil {
		h.renderError(c, http.StatusUnauthorized, "invalid_credentials", "账号或密码不正确")
		return
	}

	h.completeAuthorization(c, userInfo.Sub, clientID, redirectURI, responseType, scope, state, nonce)
}

// HandleQuickLogin 处理快速登录 (POST /oauth/quick-login)
func (h *OAuthHandler) HandleQuickLogin(c *gin.Context) {
	sub := c.PostForm("sub")
	clientID := c.PostForm("client_id")
	redirectURI := c.PostForm("redirect_uri")
	responseType := c.PostForm("response_type")
	scope := c.PostForm("scope")
	state := c.PostForm("state")
	nonce := c.PostForm("nonce")

	if sub == "" {
		h.renderError(c, http.StatusBadRequest, "invalid_request", "User sub is required")
		return
	}

	h.completeAuthorization(c, sub, clientID, redirectURI, responseType, scope, state, nonce)
}

func (h *OAuthHandler) completeAuthorization(
	c *gin.Context,
	sub, clientID, redirectURI, responseType, scope, state, nonce string,
) {
	// 验证客户端
	// 这里简化处理

	// 生成授权码
	code, err := h.service.CreateAuthorizationCode(clientID, redirectURI, scope, nonce, state)
	if err != nil {
		h.renderError(c, http.StatusInternalServerError, "server_error", "Failed to create authorization code")
		return
	}

	// 重定向回客户端
	redirectURL := redirectURI
	if redirectURL == "" {
		redirectURL = "/callback"
	}

	separator := "?"
	if strings.Contains(redirectURL, "?") {
		separator = "&"
	}

	redirectURL = redirectURL + separator + "code=" + code
	if state != "" {
		redirectURL += "&state=" + state
	}

	// 检查是否是 AJAX 请求
	if c.GetHeader("X-Requested-With") == "XMLHttpRequest" ||
		c.GetHeader("Accept") == "application/json" ||
		c.ContentType() == "application/json" {
		// AJAX 请求，返回 JSON
		c.JSON(http.StatusOK, gin.H{
			"redirect_uri": redirectURL,
			"code":         code,
			"state":        state,
		})
		return
	}

	// 传统表单提交，使用重定向
	c.Redirect(http.StatusFound, redirectURL)
}

// Token Token 端点 (POST /oauth/token)
func (h *OAuthHandler) Token(c *gin.Context) {
	var req models.TokenRequest
	if err := c.ShouldBind(&req); err != nil {
		h.renderTokenError(c, "invalid_request", err.Error())
		return
	}

	// 获取客户端凭证（从表单或 Basic Auth）
	clientID := req.ClientID
	clientSecret := req.ClientSecret

	if clientID == "" || clientSecret == "" {
		username, password, ok := c.Request.BasicAuth()
		if ok {
			clientID = username
			clientSecret = password
		}
	}

	switch req.GrantType {
	case "authorization_code":
		h.handleAuthorizationCodeGrant(c, req.Code, clientID, clientSecret, req.RedirectURI)

	case "refresh_token":
		h.handleRefreshTokenGrant(c, req.RefreshToken, clientID, clientSecret, req.Scope)

	case "client_credentials":
		h.handleClientCredentialsGrant(c, clientID, clientSecret, req.Scope)

	default:
		h.renderTokenError(c, "unsupported_grant_type", "Grant type not supported")
	}
}

func (h *OAuthHandler) handleAuthorizationCodeGrant(
	c *gin.Context,
	code, clientID, clientSecret, redirectURI string,
) {
	if code == "" {
		h.renderTokenError(c, "invalid_request", "Code is required")
		return
	}

	if clientID == "" || clientSecret == "" {
		h.renderTokenError(c, "invalid_client", "Client credentials are required")
		return
	}

	token, err := h.service.ExchangeCodeForToken(code, clientID, clientSecret, redirectURI)
	if err != nil {
		if oauthErr, ok := err.(*service.OAuthError); ok {
			h.renderTokenError(c, oauthErr.Code, oauthErr.Description)
		} else {
			h.renderTokenError(c, "server_error", err.Error())
		}
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"access_token":  token.AccessToken,
		"token_type":    token.TokenType,
		"expires_in":    token.ExpiresIn,
		"scope":         token.Scope,
		"refresh_token": token.RefreshToken,
	})
}

func (h *OAuthHandler) handleRefreshTokenGrant(
	c *gin.Context,
	refreshToken, clientID, clientSecret, scope string,
) {
	if refreshToken == "" {
		h.renderTokenError(c, "invalid_request", "Refresh token is required")
		return
	}

	if clientID == "" || clientSecret == "" {
		h.renderTokenError(c, "invalid_client", "Client credentials are required")
		return
	}

	token, err := h.service.RefreshAccessToken(refreshToken, clientID, clientSecret, scope)
	if err != nil {
		if oauthErr, ok := err.(*service.OAuthError); ok {
			h.renderTokenError(c, oauthErr.Code, oauthErr.Description)
		} else {
			h.renderTokenError(c, "server_error", err.Error())
		}
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"access_token":  token.AccessToken,
		"token_type":    token.TokenType,
		"expires_in":    token.ExpiresIn,
		"scope":         token.Scope,
		"refresh_token": token.RefreshToken,
	})
}

func (h *OAuthHandler) handleClientCredentialsGrant(
	c *gin.Context,
	clientID, clientSecret, scope string,
) {
	if clientID == "" || clientSecret == "" {
		h.renderTokenError(c, "invalid_client", "Client credentials are required")
		return
	}

	if scope == "" {
		scope = "openid"
	}

	token, err := h.service.ClientCredentialsGrant(clientID, clientSecret, scope)
	if err != nil {
		if oauthErr, ok := err.(*service.OAuthError); ok {
			h.renderTokenError(c, oauthErr.Code, oauthErr.Description)
		} else {
			h.renderTokenError(c, "server_error", err.Error())
		}
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"access_token": token.AccessToken,
		"token_type":   token.TokenType,
		"expires_in":   token.ExpiresIn,
		"scope":        token.Scope,
	})
}

// UserInfo 用户信息端点 (GET /oauth/userinfo)
func (h *OAuthHandler) UserInfo(c *gin.Context) {
	// 从 Authorization header 获取 token
	authHeader := c.GetHeader("Authorization")
	if authHeader == "" {
		c.JSON(http.StatusUnauthorized, models.ErrorResponse{
			Error:            "unauthorized",
			ErrorDescription: "Missing Authorization header",
		})
		return
	}

	parts := strings.SplitN(authHeader, " ", 2)
	if len(parts) != 2 || parts[0] != "Bearer" {
		c.JSON(http.StatusUnauthorized, models.ErrorResponse{
			Error:            "unauthorized",
			ErrorDescription: "Invalid Authorization header format",
		})
		return
	}

	accessToken := parts[1]

	// 验证 token
	claims, err := h.tokenManager.VerifyAccessToken(accessToken)
	if err != nil {
		c.JSON(http.StatusUnauthorized, models.ErrorResponse{
			Error:            "unauthorized",
			ErrorDescription: "Invalid or expired access token",
		})
		return
	}

	// 获取用户信息（这里返回默认用户信息）
	userInfo := models.UserInfo{
		Sub:       claims.Subject,
		Name:      "OAuth User",
		Email:     "user@example.com",
		LoginName: "oauth_user",
	}

	c.JSON(http.StatusOK, userInfo)
}

// JWKS JWKS 端点 (GET /.well-known/jwks.json)
func (h *OAuthHandler) JWKS(c *gin.Context) {
	jwk := h.tokenManager.GetJWK()
	c.JSON(http.StatusOK, gin.H{
		"keys": []map[string]interface{}{jwk},
	})
}

// WellKnownOIDC OIDC 发现端点 (GET /.well-known/openid-configuration)
func (h *OAuthHandler) WellKnownOIDC(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"issuer":                 h.issuer,
		"authorization_endpoint": h.issuer + "/oauth/authorize",
		"token_endpoint":         h.issuer + "/oauth/token",
		"userinfo_endpoint":      h.issuer + "/oauth/userinfo",
		"jwks_uri":               h.issuer + "/.well-known/jwks.json",
		"response_types_supported": []string{
			"code",
			"token",
			"id_token",
		},
		"subject_types_supported": []string{"public"},
		"id_token_signing_alg_values_supported": []string{
			"RS256",
		},
		"scopes_supported": []string{
			"openid",
			"email",
			"profile",
		},
		"token_endpoint_auth_methods_supported": []string{
			"client_secret_basic",
			"client_secret_post",
		},
		"claims_supported": []string{
			"sub",
			"name",
			"email",
			"iat",
			"exp",
		},
		"grant_types_supported": []string{
			"authorization_code",
			"refresh_token",
			"client_credentials",
		},
	})
}

// Introspect Token Introspection 端点 (POST /oauth/introspect)
func (h *OAuthHandler) Introspect(c *gin.Context) {
	token := c.PostForm("token")
	// tokenTypeHint := c.PostForm("token_type_hint") // 暂不使用

	if token == "" {
		c.JSON(http.StatusBadRequest, gin.H{"active": false})
		return
	}

	// 验证 token
	claims, err := h.tokenManager.VerifyAccessToken(token)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{"active": false})
		return
	}

	c.JSON(http.StatusOK, models.TokenIntrospectionResponse{
		Active:    true,
		Scope:     claims.Scope,
		ClientID:  claims.Audience[0],
		TokenType: "Bearer",
		Exp:       claims.ExpiresAt.Unix(),
		Iat:       claims.IssuedAt.Unix(),
		Sub:       claims.Subject,
		Iss:       claims.Issuer,
	})
}

func (h *OAuthHandler) renderError(c *gin.Context, status int, errCode, description string) {
	// 检查是否是 AJAX 请求
	if c.GetHeader("X-Requested-With") == "XMLHttpRequest" ||
		c.GetHeader("Accept") == "application/json" ||
		c.ContentType() == "application/json" {
		// AJAX 请求，返回 JSON
		c.JSON(status, models.ErrorResponse{
			Error:            errCode,
			ErrorDescription: description,
		})
		return
	}

	// 传统请求，返回 HTML
	c.HTML(status, "error.html", gin.H{
		"Error":       errCode,
		"Description": description,
	})
}

func (h *OAuthHandler) renderTokenError(c *gin.Context, errCode, description string) {
	c.JSON(http.StatusBadRequest, models.ErrorResponse{
		Error:            errCode,
		ErrorDescription: description,
	})
}
