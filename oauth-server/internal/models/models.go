package models

import (
	"time"
)

// OAuthClient OAuth 客户端
type OAuthClient struct {
	ClientID     string    `json:"client_id"`
	ClientSecret string    `json:"client_secret"`
	Name         string    `json:"name"`
	RedirectURIs []string  `json:"redirect_uris"`
	Scopes       []string  `json:"scopes"`
	IsActive     bool      `json:"is_active"`
	CreatedAt    time.Time `json:"created_at"`
}

// AuthorizationCode 授权码
type AuthorizationCode struct {
	Code        string    `json:"code"`
	ClientID    string    `json:"client_id"`
	RedirectURI string    `json:"redirect_uri"`
	Scope       string    `json:"scope"`
	Nonce       string    `json:"nonce"`
	State       string    `json:"state"`
	Subject     string    `json:"subject"`
	ExpiresAt   time.Time `json:"expires_at"`
	Used        bool      `json:"used"`
}

// AccessToken 访问令牌
type AccessToken struct {
	TokenType    string    `json:"token_type"`
	AccessToken  string    `json:"access_token"`
	RefreshToken string    `json:"refresh_token,omitempty"`
	IDToken      string    `json:"id_token,omitempty"`
	ExpiresIn    int       `json:"expires_in"`
	Scope        string    `json:"scope"`
	ClientID     string    `json:"client_id"`
	Subject      string    `json:"sub,omitempty"`
	CreatedAt    time.Time `json:"created_at"`
	ExpiresAt    time.Time `json:"expires_at"`
}

// RefreshToken 刷新令牌
type RefreshToken struct {
	Token       string    `json:"token"`
	AccessToken string    `json:"access_token"`
	ClientID    string    `json:"client_id"`
	Scope       string    `json:"scope"`
	ExpiresAt   time.Time `json:"expires_at"`
	Used        bool      `json:"used"`
}

// UserInfo 用户信息
type UserInfo struct {
	Sub                     string  `json:"sub"`
	Name                    string  `json:"name"`
	Email                   string  `json:"email,omitempty"`
	Avatar                  string  `json:"avatar,omitempty"`
	LoginName               string  `json:"login_name,omitempty"`
	Phone                   string  `json:"phone,omitempty"`
	Role                    string  `json:"role,omitempty"`
	RoleName                string  `json:"role_name,omitempty"`
	Department              string  `json:"department,omitempty"`
	DepartmentName          string  `json:"department_name,omitempty"`
	DepartmentStructureName string  `json:"department_structure_name,omitempty"`
	Mobile                  string  `json:"mobile,omitempty"`
	EnterpriseName          string  `json:"enterprise_name,omitempty"`
	Enterprise              string  `json:"enterprise,omitempty"`
	EnterpriseBalance       float64 `json:"enterprise_balance,omitempty"`
}

// TokenIntrospectionResponse Token  introspection 响应
type TokenIntrospectionResponse struct {
	Active    bool   `json:"active"`
	Scope     string `json:"scope,omitempty"`
	ClientID  string `json:"client_id,omitempty"`
	Username  string `json:"username,omitempty"`
	TokenType string `json:"token_type,omitempty"`
	Exp       int64  `json:"exp,omitempty"`
	Iat       int64  `json:"iat,omitempty"`
	Nbf       int64  `json:"nbf,omitempty"`
	Sub       string `json:"sub,omitempty"`
	Aud       string `json:"aud,omitempty"`
	Iss       string `json:"iss,omitempty"`
	Jti       string `json:"jti,omitempty"`
}

// JWKS JSON Web Key Set
type JWKS struct {
	Keys []JWK `json:"keys"`
}

// JWK JSON Web Key
type JWK struct {
	Kty string `json:"kty"`
	Kid string `json:"kid"`
	Use string `json:"use"`
	Alg string `json:"alg"`
	N   string `json:"n"`
	E   string `json:"e"`
}

// ErrorResponse 错误响应
type ErrorResponse struct {
	Error            string `json:"error"`
	ErrorDescription string `json:"error_description,omitempty"`
	ErrorURI         string `json:"error_uri,omitempty"`
}

// AuthRequest 授权请求参数
type AuthRequest struct {
	ClientID     string `form:"client_id" binding:"required"`
	RedirectURI  string `form:"redirect_uri"`
	ResponseType string `form:"response_type" binding:"required"`
	Scope        string `form:"scope"`
	State        string `form:"state"`
	Nonce        string `form:"nonce"`
}

// LoginRequest 登录请求参数
type LoginRequest struct {
	Username     string `form:"username" binding:"required"`
	Password     string `form:"password" binding:"required"`
	ClientID     string `form:"client_id"`
	RedirectURI  string `form:"redirect_uri"`
	ResponseType string `form:"response_type"`
	Scope        string `form:"scope"`
	State        string `form:"state"`
	Nonce        string `form:"nonce"`
}

// TokenRequest Token 请求参数
type TokenRequest struct {
	GrantType    string `form:"grant_type" binding:"required"`
	Code         string `form:"code"`
	RedirectURI  string `form:"redirect_uri"`
	ClientID     string `form:"client_id"`
	ClientSecret string `form:"client_secret"`
	Scope        string `form:"scope"`
	RefreshToken string `form:"refresh_token"`
}
