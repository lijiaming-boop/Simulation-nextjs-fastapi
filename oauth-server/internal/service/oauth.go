package service

import (
	"time"

	"oauth-server/internal/models"
	"oauth-server/internal/store"
	"oauth-server/internal/token"
)

// OAuthService OAuth 服务
type OAuthService struct {
	store        store.Store
	tokenManager *token.TokenManager
	issuer       string
}

// NewOAuthService 创建新的 OAuth 服务
func NewOAuthService(store store.Store, tokenManager *token.TokenManager, issuer string) *OAuthService {
	return &OAuthService{
		store:        store,
		tokenManager: tokenManager,
		issuer:       issuer,
	}
}

// CreateAuthorizationCode 创建授权码
func (s *OAuthService) CreateAuthorizationCode(clientID, redirectURI, scope, nonce, state string) (string, error) {
	code, err := s.tokenManager.GenerateAuthorizationCode()
	if err != nil {
		return "", err
	}

	authCode := &models.AuthorizationCode{
		Code:        code,
		ClientID:    clientID,
		RedirectURI: redirectURI,
		Scope:       scope,
		Nonce:       nonce,
		State:       state,
		ExpiresAt:   time.Now().Add(10 * time.Minute), // 10 分钟有效期
		Used:        false,
	}

	s.store.SaveAuthCode(authCode)
	return code, nil
}

// ExchangeCodeForToken 用授权码交换令牌
func (s *OAuthService) ExchangeCodeForToken(code, clientID, clientSecret, redirectURI string) (*models.AccessToken, error) {
	// 验证客户端
	_, exists := s.store.GetClientBySecret(clientID, clientSecret)
	if !exists {
		return nil, &OAuthError{
			Code:        "invalid_client",
			Description: "Invalid client credentials",
		}
	}

	// 获取并验证授权码
	authCode, exists := s.store.GetAuthCode(code)
	if !exists {
		return nil, &OAuthError{
			Code:        "invalid_grant",
			Description: "Invalid or expired authorization code",
		}
	}

	// 验证 client_id
	if authCode.ClientID != clientID {
		return nil, &OAuthError{
			Code:        "invalid_grant",
			Description: "Client ID mismatch",
		}
	}

	// 验证 redirect_uri
	if redirectURI != "" && redirectURI != authCode.RedirectURI {
		return nil, &OAuthError{
			Code:        "redirect_uri_mismatch",
			Description: "Redirect URI mismatch",
		}
	}

	// 标记授权码已使用
	authCode.Used = true
	s.store.DeleteAuthCode(code)

	// 生成访问令牌
	accessTokenString, err := s.tokenManager.GenerateAccessToken(
		clientID,
		"authenticated-user", // 默认用户，实际应该从授权码中获取
		authCode.Scope,
		3600*time.Second, // 1 小时有效期
	)
	if err != nil {
		return nil, err
	}

	// 生成刷新令牌
	refreshTokenString, err := s.tokenManager.GenerateRefreshToken(
		clientID,
		"authenticated-user",
		authCode.Scope,
		7*24*time.Hour, // 7 天有效期
	)
	if err != nil {
		return nil, err
	}

	now := time.Now()
	token := &models.AccessToken{
		TokenType:    "Bearer",
		AccessToken:  accessTokenString,
		RefreshToken: refreshTokenString,
		ExpiresIn:    3600,
		Scope:        authCode.Scope,
		ClientID:     clientID,
		Subject:      "authenticated-user",
		CreatedAt:    now,
		ExpiresAt:    now.Add(3600 * time.Second),
	}

	s.store.SaveToken(token)

	// 保存刷新令牌
	s.store.SaveRefreshToken(&models.RefreshToken{
		Token:       refreshTokenString,
		AccessToken: accessTokenString,
		ClientID:    clientID,
		Scope:       authCode.Scope,
		ExpiresAt:   now.Add(7 * 24 * time.Hour),
		Used:        false,
	})

	return token, nil
}

// RefreshAccessToken 刷新访问令牌
func (s *OAuthService) RefreshAccessToken(refreshToken, clientID, clientSecret, scope string) (*models.AccessToken, error) {
	// 验证客户端
	_, exists := s.store.GetClientBySecret(clientID, clientSecret)
	if !exists {
		return nil, &OAuthError{
			Code:        "invalid_client",
			Description: "Invalid client credentials",
		}
	}

	// 获取并验证刷新令牌
	storedToken, exists := s.store.GetRefreshToken(refreshToken)
	if !exists {
		return nil, &OAuthError{
			Code:        "invalid_grant",
			Description: "Invalid or expired refresh token",
		}
	}

	// 验证 client_id
	if storedToken.ClientID != clientID {
		return nil, &OAuthError{
			Code:        "invalid_grant",
			Description: "Client ID mismatch",
		}
	}

	// 标记旧刷新令牌已使用
	storedToken.Used = true
	s.store.DeleteRefreshToken(refreshToken)

	// 使用新的刷新令牌
	newRefreshTokenString, err := s.tokenManager.GenerateRefreshToken(
		clientID,
		storedToken.Token,
		storedToken.Scope,
		7*24*time.Hour,
	)
	if err != nil {
		return nil, err
	}

	// 生成新的访问令牌
	accessTokenString, err := s.tokenManager.GenerateAccessToken(
		clientID,
		storedToken.Token,
		storedToken.Scope,
		3600*time.Second,
	)
	if err != nil {
		return nil, err
	}

	now := time.Now()
	token := &models.AccessToken{
		TokenType:    "Bearer",
		AccessToken:  accessTokenString,
		RefreshToken: newRefreshTokenString,
		ExpiresIn:    3600,
		Scope:        storedToken.Scope,
		ClientID:     clientID,
		Subject:      storedToken.Token,
		CreatedAt:    now,
		ExpiresAt:    now.Add(3600 * time.Second),
	}

	s.store.SaveToken(token)

	// 保存新的刷新令牌
	s.store.SaveRefreshToken(&models.RefreshToken{
		Token:       newRefreshTokenString,
		AccessToken: accessTokenString,
		ClientID:    clientID,
		Scope:       storedToken.Scope,
		ExpiresAt:   now.Add(7 * 24 * time.Hour),
		Used:        false,
	})

	return token, nil
}

// ClientCredentialsGrant 客户端凭证模式
func (s *OAuthService) ClientCredentialsGrant(clientID, clientSecret, scope string) (*models.AccessToken, error) {
	// 验证客户端
	_, exists := s.store.GetClientBySecret(clientID, clientSecret)
	if !exists {
		return nil, &OAuthError{
			Code:        "invalid_client",
			Description: "Invalid client credentials",
		}
	}

	// 生成访问令牌（没有刷新令牌）
	accessTokenString, err := s.tokenManager.GenerateAccessToken(
		clientID,
		clientID, // 客户端凭证模式下，subject 为 client_id
		scope,
		3600*time.Second,
	)
	if err != nil {
		return nil, err
	}

	now := time.Now()
	token := &models.AccessToken{
		TokenType:   "Bearer",
		AccessToken: accessTokenString,
		ExpiresIn:   3600,
		Scope:       scope,
		ClientID:    clientID,
		Subject:     clientID,
		CreatedAt:   now,
		ExpiresAt:   now.Add(3600 * time.Second),
	}

	s.store.SaveToken(token)
	return token, nil
}

// ValidateToken 验证令牌
func (s *OAuthService) ValidateToken(accessToken string) (*token.JWTClaims, error) {
	return s.tokenManager.VerifyAccessToken(accessToken)
}

// GetClient 获取客户端
func (s *OAuthService) GetClient(clientID string) (*models.OAuthClient, bool) {
	return s.store.GetClient(clientID)
}

// GetUserInfo 获取用户信息
func (s *OAuthService) GetUserInfo(sub string) (*models.UserInfo, bool) {
	return s.store.GetUser(sub)
}

// OAuthError OAuth 错误
type OAuthError struct {
	Code        string
	Description string
	URI         string
}

func (e *OAuthError) Error() string {
	return e.Description
}
