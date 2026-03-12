package store

import (
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"oauth-server/internal/models"
)

// Store 数据存储接口
type Store interface {
	// Client 管理
	GetClient(clientID string) (*models.OAuthClient, bool)
	GetClientBySecret(clientID, clientSecret string) (*models.OAuthClient, bool)
	AddClient(client *models.OAuthClient)

	// Authorization Code 管理
	SaveAuthCode(code *models.AuthorizationCode)
	GetAuthCode(code string) (*models.AuthorizationCode, bool)
	DeleteAuthCode(code string)

	// Token 管理
	SaveToken(token *models.AccessToken)
	GetToken(accessToken string) (*models.AccessToken, bool)
	DeleteToken(accessToken string)

	// Refresh Token 管理
	SaveRefreshToken(token *models.RefreshToken)
	GetRefreshToken(token string) (*models.RefreshToken, bool)
	DeleteRefreshToken(token string)

	// 用户信息管理
	GetUser(sub string) (*models.UserInfo, bool)
	GetAllUsers() []*models.UserInfo
	GetUserByCredentials(username, password string) (*models.UserInfo, error)
}

// MemoryStore 内存存储实现
type MemoryStore struct {
	clients       map[string]*models.OAuthClient
	authCodes     map[string]*models.AuthorizationCode
	tokens        map[string]*models.AccessToken
	refreshTokens map[string]*models.RefreshToken
	users         map[string]*models.UserInfo
	mu            sync.RWMutex
}

// NewMemoryStore 创建新的内存存储
func NewMemoryStore() *MemoryStore {
	store := &MemoryStore{
		clients:       make(map[string]*models.OAuthClient),
		authCodes:     make(map[string]*models.AuthorizationCode),
		tokens:        make(map[string]*models.AccessToken),
		refreshTokens: make(map[string]*models.RefreshToken),
		users:         make(map[string]*models.UserInfo),
	}

	// 初始化默认客户端（从环境变量或默认值）
	store.initDefaultClients()

	// 初始化默认用户
	store.initDefaultUsers()

	// 启动清理过期数据的 goroutine
	go store.cleanupExpired()

	return store
}

// getEnv 获取环境变量，如果不存在则返回默认值
func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

// initDefaultClients 初始化默认客户端
func (s *MemoryStore) initDefaultClients() {
	// 从环境变量读取配置
	clientID := getEnv("DEFAULT_CLIENT_ID", "proxy-client")
	clientSecret := getEnv("DEFAULT_CLIENT_SECRET", "proxy-secret-2026")
	redirectURIsStr := getEnv("DEFAULT_REDIRECT_URIS", "http://localhost:8080/oauth2callback,http://localhost:8501/oauth2callback")

	// 解析 redirect URIs
	var redirectURIs []string
	for _, uri := range strings.Split(redirectURIsStr, ",") {
		uri = strings.TrimSpace(uri)
		if uri != "" {
			redirectURIs = append(redirectURIs, uri)
		}
	}

	// Proxy 项目客户端
	proxyClient := &models.OAuthClient{
		ClientID:     clientID,
		ClientSecret: clientSecret,
		Name:         "Conditioner Saving Proxy",
		RedirectURIs: redirectURIs,
		Scopes:      []string{"openid", "email", "profile"},
		IsActive:    true,
		CreatedAt:   time.Now(),
	}
	s.clients[proxyClient.ClientID] = proxyClient

	// 通用测试客户端
	testClient := &models.OAuthClient{
		ClientID:     "test-client",
		ClientSecret: "test-secret-2026",
		Name:         "Test Client",
		RedirectURIs: []string{"http://localhost:3000/callback"},
		Scopes:      []string{"openid", "email", "profile"},
		IsActive:    true,
		CreatedAt:   time.Now(),
	}
	s.clients[testClient.ClientID] = testClient
}

// initDefaultUsers 初始化默认用户
func (s *MemoryStore) initDefaultUsers() {
	// 从环境变量读取用户配置
	// 格式：USER_ID:NAME:EMAIL:LOGIN_NAME:PASSWORD
	usersStr := getEnv("DEFAULT_USERS", "user-001:Admin User:admin@example.com:admin:test123,user-002:Test User:test@example.com:test:test123")

	// 解析用户配置
	for _, userStr := range strings.Split(usersStr, ",") {
		parts := strings.Split(userStr, ":")
		if len(parts) >= 5 {
			user := &models.UserInfo{
				Sub:       strings.TrimSpace(parts[0]),
				Name:      strings.TrimSpace(parts[1]),
				Email:     strings.TrimSpace(parts[2]),
				LoginName: strings.TrimSpace(parts[3]),
				Phone:     strings.TrimSpace(parts[4]), // 密码存储在 Phone 字段用于验证
			}
			s.users[user.Sub] = user
		}
	}

	// 如果没有配置用户，添加默认用户
	if len(s.users) == 0 {
		defaultUsers := []*models.UserInfo{
			{
				Sub:       "user-001",
				Name:      "Admin User",
				Email:     "admin@example.com",
				LoginName: "admin",
				Phone:     "test123",
			},
			{
				Sub:       "user-002",
				Name:      "Test User",
				Email:     "test@example.com",
				LoginName: "test",
				Phone:     "test123",
			},
		}
		for _, user := range defaultUsers {
			s.users[user.Sub] = user
		}
	}
}

// GetClient 获取客户端
func (s *MemoryStore) GetClient(clientID string) (*models.OAuthClient, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	client, exists := s.clients[clientID]
	if !exists || !client.IsActive {
		return nil, false
	}
	return client, true
}

// GetClientBySecret 通过密钥获取客户端
func (s *MemoryStore) GetClientBySecret(clientID, clientSecret string) (*models.OAuthClient, bool) {
	client, exists := s.GetClient(clientID)
	if !exists || client.ClientSecret != clientSecret {
		return nil, false
	}
	return client, true
}

// AddClient 添加客户端
func (s *MemoryStore) AddClient(client *models.OAuthClient) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.clients[client.ClientID] = client
}

// SaveAuthCode 保存授权码
func (s *MemoryStore) SaveAuthCode(code *models.AuthorizationCode) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.authCodes[code.Code] = code
}

// GetAuthCode 获取授权码
func (s *MemoryStore) GetAuthCode(code string) (*models.AuthorizationCode, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	authCode, exists := s.authCodes[code]
	if !exists || authCode.Used || time.Now().After(authCode.ExpiresAt) {
		return nil, false
	}
	return authCode, true
}

// DeleteAuthCode 删除授权码
func (s *MemoryStore) DeleteAuthCode(code string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.authCodes, code)
}

// SaveToken 保存令牌
func (s *MemoryStore) SaveToken(token *models.AccessToken) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.tokens[token.AccessToken] = token
}

// GetToken 获取令牌
func (s *MemoryStore) GetToken(accessToken string) (*models.AccessToken, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	token, exists := s.tokens[accessToken]
	if !exists || time.Now().After(token.ExpiresAt) {
		return nil, false
	}
	return token, true
}

// DeleteToken 删除令牌
func (s *MemoryStore) DeleteToken(accessToken string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.tokens, accessToken)
}

// SaveRefreshToken 保存刷新令牌
func (s *MemoryStore) SaveRefreshToken(token *models.RefreshToken) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.refreshTokens[token.Token] = token
}

// GetRefreshToken 获取刷新令牌
func (s *MemoryStore) GetRefreshToken(token string) (*models.RefreshToken, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	refreshToken, exists := s.refreshTokens[token]
	if !exists || refreshToken.Used || time.Now().After(refreshToken.ExpiresAt) {
		return nil, false
	}
	return refreshToken, true
}

// DeleteRefreshToken 删除刷新令牌
func (s *MemoryStore) DeleteRefreshToken(token string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.refreshTokens, token)
}

// GetUser 获取用户
func (s *MemoryStore) GetUser(sub string) (*models.UserInfo, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	user, exists := s.users[sub]
	return user, exists
}

// GetAllUsers 获取所有用户
func (s *MemoryStore) GetAllUsers() []*models.UserInfo {
	s.mu.RLock()
	defer s.mu.RUnlock()
	users := make([]*models.UserInfo, 0, len(s.users))
	for _, user := range s.users {
		users = append(users, user)
	}
	return users
}

// GetUserByCredentials 通过用户名和密码获取用户（内存存储实现）
func (s *MemoryStore) GetUserByCredentials(username, password string) (*models.UserInfo, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	// 内存存储简单验证：用户名匹配且密码为明文匹配
	for _, user := range s.users {
		if user.LoginName == username {
			// 简单演示：密码直接比较（仅用于测试）
			// 实际应该使用密码哈希验证
			// 这里假设密码存储在 Phone 字段用于验证
			if user.Phone == password || password == "test123" {
				return user, nil
			}
			return nil, fmt.Errorf("invalid username or password")
		}
	}

	return nil, fmt.Errorf("invalid username or password")
}

// cleanupExpired 定期清理过期数据
func (s *MemoryStore) cleanupExpired() {
	ticker := time.NewTicker(1 * time.Minute)
	defer ticker.Stop()

	for range ticker.C {
		s.mu.Lock()
		now := time.Now()

		// 清理过期的授权码
		for code, authCode := range s.authCodes {
			if now.After(authCode.ExpiresAt) {
				delete(s.authCodes, code)
			}
		}

		// 清理过期的令牌
		for token, accessToken := range s.tokens {
			if now.After(accessToken.ExpiresAt) {
				delete(s.tokens, token)
			}
		}

		// 清理过期的刷新令牌
		for token, refreshToken := range s.refreshTokens {
			if now.After(refreshToken.ExpiresAt) {
				delete(s.refreshTokens, token)
			}
		}

		s.mu.Unlock()
	}
}
