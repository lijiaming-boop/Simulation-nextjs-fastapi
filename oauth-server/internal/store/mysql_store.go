package store

import (
	"database/sql"
	"fmt"
	"strings"
	"sync"
	"time"

	"oauth-server/internal/models"
	pw "oauth-server/internal/password"

	_ "github.com/go-sql-driver/mysql"
)

// MySQLStore MySQL 存储实现
type MySQLStore struct {
	db            *sql.DB
	clients       map[string]*models.OAuthClient
	authCodes     map[string]*models.AuthorizationCode
	tokens        map[string]*models.AccessToken
	refreshTokens map[string]*models.RefreshToken
	mu            sync.RWMutex
}

// MySQLConfig MySQL 配置
type MySQLConfig struct {
	Host     string
	Port     string
	Database string
	User     string
	Password string
}

// NewMySQLStore 创建新的 MySQL 存储
func NewMySQLStore() (*MySQLStore, error) {
	// 从环境变量读取配置
	config := MySQLConfig{
		Host:     getEnv("MYSQL_HOST", "localhost"),
		Port:     getEnv("MYSQL_PORT", "13306"),
		Database: getEnv("MYSQL_DATABASE", "mglink_selfiem"),
		User:     getEnv("MYSQL_USER", "root"),
		Password: getEnv("MYSQL_PASSWORD", ""),
	}

	// 构建 DSN
	dsn := fmt.Sprintf("%s:%s@tcp(%s:%s)/%s?charset=utf8mb4&parseTime=True&loc=Local",
		config.User,
		config.Password,
		config.Host,
		config.Port,
		config.Database,
	)

	// 连接数据库
	db, err := sql.Open("mysql", dsn)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	// 测试连接
	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	// 设置连接池参数
	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(5 * time.Minute)

	store := &MySQLStore{
		db:            db,
		clients:       make(map[string]*models.OAuthClient),
		authCodes:     make(map[string]*models.AuthorizationCode),
		tokens:        make(map[string]*models.AccessToken),
		refreshTokens: make(map[string]*models.RefreshToken),
	}

	// 初始化默认客户端
	store.initDefaultClients()

	// 启动清理过期数据的 goroutine
	go store.cleanupExpired()

	return store, nil
}

// initDefaultClients 初始化默认客户端
func (s *MySQLStore) initDefaultClients() {
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
		Scopes:       []string{"openid", "email", "profile"},
		IsActive:     true,
		CreatedAt:    time.Now(),
	}
	s.clients[proxyClient.ClientID] = proxyClient

	// 通用测试客户端
	testClient := &models.OAuthClient{
		ClientID:     "test-client",
		ClientSecret: "test-secret-2026",
		Name:         "Test Client",
		RedirectURIs: []string{"http://localhost:3000/callback"},
		Scopes:       []string{"openid", "email", "profile"},
		IsActive:     true,
		CreatedAt:    time.Now(),
	}
	s.clients[testClient.ClientID] = testClient
}

// GetUserByCredentials 通过用户名和密码获取用户
func (s *MySQLStore) GetUserByCredentials(username, password string) (*models.UserInfo, error) {
	// 查询 bas_enterprise_user 表
	// 假设表结构包含：login_name, user_password, user_salt, user_id, user_name, email, mobile 等字段
	query := `
		SELECT user_id, user_name, email, mobile, avatar_url, user_password, user_salt 
		FROM bas_enterprise_user 
		WHERE login_name = ? AND is_deleted = 0
	`

	var userID, userName, email, mobile, avatarURL sql.NullString
	var storedHash, storedSalt sql.NullString
	err := s.db.QueryRow(query, username).Scan(
		&userID,
		&userName,
		&email,
		&mobile,
		&avatarURL,
		&storedHash,
		&storedSalt,
	)

	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("账号或密码不正确")
	}
	if err != nil {
		return nil, fmt.Errorf("database error: %w", err)
	}

	// 验证密码
	if !storedHash.Valid || !storedSalt.Valid {
		return nil, fmt.Errorf("账号或密码不正确")
	}

	if !pw.CheckPassword(password, storedSalt.String, storedHash.String) {
		return nil, fmt.Errorf("账号或密码不正确")
	}

	userInfo := &models.UserInfo{
		Sub:       userID.String,
		Name:      userName.String,
		Email:     email.String,
		Phone:     mobile.String,
		Avatar:    avatarURL.String,
		LoginName: username,
	}

	return userInfo, nil
}

// GetUserByID 通过用户 ID 获取用户
func (s *MySQLStore) GetUserByID(userID string) (*models.UserInfo, error) {
	query := `
		SELECT user_id, user_name, email, mobile, avatar_url, login_name 
		FROM bas_enterprise_user 
		WHERE user_id = ? AND is_deleted = 0
	`

	var sub, userName, email, mobile, avatarURL, loginName sql.NullString
	err := s.db.QueryRow(query, userID).Scan(
		&sub,
		&userName,
		&email,
		&mobile,
		&avatarURL,
		&loginName,
	)

	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("user not found")
	}
	if err != nil {
		return nil, fmt.Errorf("database error: %w", err)
	}

	userInfo := &models.UserInfo{
		Sub:       sub.String,
		Name:      userName.String,
		Email:     email.String,
		Phone:     mobile.String,
		Avatar:    avatarURL.String,
		LoginName: loginName.String,
	}

	return userInfo, nil
}

// GetClient 获取客户端
func (s *MySQLStore) GetClient(clientID string) (*models.OAuthClient, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	client, exists := s.clients[clientID]
	if !exists || !client.IsActive {
		return nil, false
	}
	return client, true
}

// GetClientBySecret 通过密钥获取客户端
func (s *MySQLStore) GetClientBySecret(clientID, clientSecret string) (*models.OAuthClient, bool) {
	client, exists := s.GetClient(clientID)
	if !exists || client.ClientSecret != clientSecret {
		return nil, false
	}
	return client, true
}

// AddClient 添加客户端
func (s *MySQLStore) AddClient(client *models.OAuthClient) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.clients[client.ClientID] = client
}

// SaveAuthCode 保存授权码
func (s *MySQLStore) SaveAuthCode(code *models.AuthorizationCode) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.authCodes[code.Code] = code
}

// GetAuthCode 获取授权码
func (s *MySQLStore) GetAuthCode(code string) (*models.AuthorizationCode, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	authCode, exists := s.authCodes[code]
	if !exists || authCode.Used || time.Now().After(authCode.ExpiresAt) {
		return nil, false
	}
	return authCode, true
}

// DeleteAuthCode 删除授权码
func (s *MySQLStore) DeleteAuthCode(code string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.authCodes, code)
}

// SaveToken 保存令牌
func (s *MySQLStore) SaveToken(token *models.AccessToken) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.tokens[token.AccessToken] = token
}

// GetToken 获取令牌
func (s *MySQLStore) GetToken(accessToken string) (*models.AccessToken, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	token, exists := s.tokens[accessToken]
	if !exists || time.Now().After(token.ExpiresAt) {
		return nil, false
	}
	return token, true
}

// DeleteToken 删除令牌
func (s *MySQLStore) DeleteToken(accessToken string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.tokens, accessToken)
}

// SaveRefreshToken 保存刷新令牌
func (s *MySQLStore) SaveRefreshToken(token *models.RefreshToken) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.refreshTokens[token.Token] = token
}

// GetRefreshToken 获取刷新令牌
func (s *MySQLStore) GetRefreshToken(token string) (*models.RefreshToken, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	refreshToken, exists := s.refreshTokens[token]
	if !exists || refreshToken.Used || time.Now().After(refreshToken.ExpiresAt) {
		return nil, false
	}
	return refreshToken, true
}

// DeleteRefreshToken 删除刷新令牌
func (s *MySQLStore) DeleteRefreshToken(token string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.refreshTokens, token)
}

// GetUser 获取用户（通过 sub）
func (s *MySQLStore) GetUser(sub string) (*models.UserInfo, bool) {
	userInfo, err := s.GetUserByID(sub)
	if err != nil {
		return nil, false
	}
	return userInfo, true
}

// GetAllUsers 获取所有用户（内存存储，用于兼容）
func (s *MySQLStore) GetAllUsers() []*models.UserInfo {
	s.mu.RLock()
	defer s.mu.RUnlock()
	users := make([]*models.UserInfo, 0)
	return users
}

// cleanupExpired 定期清理过期数据
func (s *MySQLStore) cleanupExpired() {
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

// Close 关闭数据库连接
func (s *MySQLStore) Close() error {
	if s.db != nil {
		return s.db.Close()
	}
	return nil
}
