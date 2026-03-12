package password

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"math/big"
	mrand "math/rand"
	"time"
)

// PasswordPair 密码对
type PasswordPair struct {
	Password string // 密码哈希
	Salt     string // 盐
}

// encode 编码密码
// 逻辑与 Java 实现一致：
// 1. 截取明文密码前两位和后两位
// 2. 组合：前两位 + 盐 + 完整密码 + 后两位
// 3. SHA-256 哈希
func encode(password, salt string) (*PasswordPair, error) {
	if len(password) < 2 {
		return nil, fmt.Errorf("password too short")
	}

	// 截取明文密码前两位和后两位
	front := password[:2]
	end := password[len(password)-2:]

	// 如果盐为空，生成随机盐
	if salt == "" {
		salt = generateSalt()
	}

	// 组合：前两位 + 盐 + 完整密码 + 后两位
	combined := front + salt + password + end

	// SHA-256 哈希
	hash := sha256.Sum256([]byte(combined))
	passwordHex := hex.EncodeToString(hash[:])

	return &PasswordPair{
		Password: passwordHex,
		Salt:     salt,
	}, nil
}

// generateSalt 生成随机盐
// 生成 260 位的随机数，转换为 32 进制字符串
func generateSalt() string {
	// 260 位，相当于 Java 的 BigInteger(260, random)
	max := new(big.Int).Exp(big.NewInt(2), big.NewInt(260), nil)
	n, err := rand.Int(rand.Reader, max)
	if err != nil {
		// fallback 到简单随机
		mrand.Seed(time.Now().UnixNano())
		n = big.NewInt(int64(mrand.Intn(1000000)))
	}
	return n.Text(32)
}

// CreatePassword 创建密码哈希
// 返回密码哈希和盐
func CreatePassword(password string) (*PasswordPair, error) {
	return encode(password, "")
}

// CheckPassword 验证密码
// password: 用户输入的明文密码
// salt: 数据库中存储的盐
// correctHash: 数据库中存储的密码哈希
func CheckPassword(password, salt, correctHash string) bool {
	pair, err := encode(password, salt)
	if err != nil {
		return false
	}
	return pair.Password == correctHash
}
