package token

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"math/big"
	"sync"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// JWTClaims JWT Claims 结构
type JWTClaims struct {
	jwt.RegisteredClaims
	Scope string `json:"scope,omitempty"`
	Nonce string `json:"nonce,omitempty"`
}

// TokenManager Token 管理器
type TokenManager struct {
	privateKey *rsa.PrivateKey
	publicKey  *rsa.PublicKey
	kid        string
	mu         sync.RWMutex
}

// NewTokenManager 创建新的 Token 管理器
func NewTokenManager() (*TokenManager, error) {
	// 生成 RSA 密钥对
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		return nil, fmt.Errorf("failed to generate private key: %w", err)
	}

	return &TokenManager{
		privateKey: privateKey,
		publicKey:  &privateKey.PublicKey,
		kid:        generateKID(privateKey),
	}, nil
}

// GenerateAccessToken 生成访问令牌
func (tm *TokenManager) GenerateAccessToken(clientID, subject, scope string, expiresIn time.Duration) (string, error) {
	tm.mu.RLock()
	defer tm.mu.RUnlock()

	now := time.Now()
	claims := JWTClaims{
		RegisteredClaims: jwt.RegisteredClaims{
			Issuer:    "oauth-server",
			Subject:   subject,
			Audience:  jwt.ClaimStrings{clientID},
			ExpiresAt: jwt.NewNumericDate(now.Add(expiresIn)),
			NotBefore: jwt.NewNumericDate(now),
			IssuedAt:  jwt.NewNumericDate(now),
			ID:        generateTokenID(),
		},
		Scope: scope,
	}

	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	token.Header["kid"] = tm.kid

	return token.SignedString(tm.privateKey)
}

// GenerateRefreshToken 生成刷新令牌
func (tm *TokenManager) GenerateRefreshToken(clientID, subject, scope string, expiresIn time.Duration) (string, error) {
	return generateSecureToken()
}

// GenerateIDToken 生成 ID Token (OpenID Connect)
func (tm *TokenManager) GenerateIDToken(issuer, subject, audience, nonce string, expiresIn time.Duration) (string, error) {
	tm.mu.RLock()
	defer tm.mu.RUnlock()

	now := time.Now()
	claims := JWTClaims{
		RegisteredClaims: jwt.RegisteredClaims{
			Issuer:    issuer,
			Subject:   subject,
			Audience:  jwt.ClaimStrings{audience},
			ExpiresAt: jwt.NewNumericDate(now.Add(expiresIn)),
			NotBefore: jwt.NewNumericDate(now),
			IssuedAt:  jwt.NewNumericDate(now),
			ID:        generateTokenID(),
		},
		Nonce: nonce,
	}

	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	token.Header["kid"] = tm.kid

	return token.SignedString(tm.privateKey)
}

// GenerateAuthorizationCode 生成授权码
func (tm *TokenManager) GenerateAuthorizationCode() (string, error) {
	return generateSecureToken()
}

// VerifyAccessToken 验证访问令牌
func (tm *TokenManager) VerifyAccessToken(tokenString string) (*JWTClaims, error) {
	tm.mu.RLock()
	defer tm.mu.RUnlock()

	token, err := jwt.ParseWithClaims(tokenString, &JWTClaims{}, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodRSA); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}
		return tm.publicKey, nil
	})

	if err != nil {
		return nil, err
	}

	claims, ok := token.Claims.(*JWTClaims)
	if !ok || !token.Valid {
		return nil, fmt.Errorf("invalid token claims")
	}

	return claims, nil
}

// GetPublicKey 获取公钥
func (tm *TokenManager) GetPublicKey() *rsa.PublicKey {
	tm.mu.RLock()
	defer tm.mu.RUnlock()
	return tm.publicKey
}

// GetKID 获取密钥 ID
func (tm *TokenManager) GetKID() string {
	return tm.kid
}

// GetJWK 获取 JWK
func (tm *TokenManager) GetJWK() map[string]interface{} {
	tm.mu.RLock()
	defer tm.mu.RUnlock()

	n := tm.publicKey.N
	e := tm.publicKey.E

	return map[string]interface{}{
		"kty": "RSA",
		"kid": tm.kid,
		"use": "sig",
		"alg": "RS256",
		"n":   base64.RawURLEncoding.EncodeToString(n.Bytes()),
		"e":   base64.RawURLEncoding.EncodeToString(big.NewInt(int64(e)).Bytes()),
	}
}

// generateKID 生成密钥 ID
func generateKID(privateKey *rsa.PrivateKey) string {
	// 使用公钥的 SHA256 哈希作为 KID
	publicKeyBytes := privateKey.PublicKey.N.Bytes()
	hash := sha256.Sum256(publicKeyBytes)
	return base64.RawURLEncoding.EncodeToString(hash[:16])
}

// generateTokenID 生成 Token ID
func generateTokenID() string {
	token, _ := generateSecureToken()
	return token
}

// generateSecureToken 生成安全随机令牌
func generateSecureToken() (string, error) {
	bytes := make([]byte, 32)
	if _, err := rand.Read(bytes); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(bytes), nil
}

// EncodeToBase64URL 将大整数编码为 base64url
func EncodeToBase64URL(n *big.Int) string {
	return base64.RawURLEncoding.EncodeToString(n.Bytes())
}
