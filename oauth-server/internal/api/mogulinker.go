package api

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

// MogulinkerAPIClient 蘑菇物联 API 客户端
type MogulinkerAPIClient struct {
	baseURL    string
	domain     string
	httpClient *http.Client
}

// LoginRequest 登录请求
type LoginRequest struct {
	Mobile   string `json:"mobile"`
	Pwd      string `json:"pwd"`
	Platform string `json:"platform"`
	Domain   string `json:"domain"`
}

// LoginResponse 登录响应
type LoginResponse struct {
	TraceID string     `json:"traceId"`
	Code    string     `json:"code"`
	Message string     `json:"message"`
	Data    *LoginData `json:"data"`
}

// LoginData 登录数据
type LoginData struct {
	Token                    string  `json:"token"`
	UserID                   string  `json:"userId"`
	UserName                 string  `json:"userName"`
	Role                     string  `json:"role"`
	RoleName                 string  `json:"roleName"`
	Department               string  `json:"department"`
	DepartmentName           string  `json:"departmentName"`
	DepartmentStructureName  string  `json:"departmentStructureName"`
	Mobile                   string  `json:"mobile"`
	EnterpriseName           string  `json:"enterpriseName"`
	Enterprise               string  `json:"enterprise"`
	EnterpriseBalance        float64 `json:"enterpriseBalance"`
	UserHeaderImageURL       *string `json:"userHeaderImageUrl"`
	EnterpriseHeaderImageURL string  `json:"enterpriseHeaderImageUrl"`
	EnterpriseIsErp          bool    `json:"enterpriseIsErp"`
	EnterpriseAppVersion     int     `json:"enterpriseAppVersion"`
	IsNeedPrivacy            bool    `json:"isNeedPrivacy"`
	QiniuURL                 string  `json:"qiniuUrl"`
	QiniuUploadURL           string  `json:"qiniuUploadUrl"`
	OnTest                   bool    `json:"onTest"`
	WorkBenchAuthRole        string  `json:"workBenchAuthRole"`
	WorkBenchAuthRoleName    string  `json:"workBenchAuthRoleName"`
	ProfitAuth               string  `json:"profitAuth"`
}

// NewMogulinkerAPIClient 创建新的 API 客户端
func NewMogulinkerAPIClient() *MogulinkerAPIClient {
	// 从环境变量读取配置，如果没有则使用默认值
	baseURL := getEnv("MOGULINKER_API_BASE_URL", "https://h-api.mogulinker.com")
	domain := getEnv("MOGULINKER_API_DOMAIN", "h.mogulinker.com")

	return &MogulinkerAPIClient{
		baseURL: baseURL,
		domain:  domain,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// getEnv 获取环境变量，如果不存在则返回默认值
func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

// Login 调用登录接口
func (c *MogulinkerAPIClient) Login(mobile, password string) (*LoginData, error) {
	// 构建请求体
	reqBody := LoginRequest{
		Mobile:   mobile,
		Pwd:      password,
		Platform: "pc",
		Domain:   c.domain,
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	// 创建 HTTP 请求
	url := c.baseURL + "/cloud/iem/v1/enterpriseUser/login"
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	// 设置请求头
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	// 发送请求
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	// 读取响应体
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %w", err)
	}

	// 解析响应
	var loginResp LoginResponse
	if err := json.Unmarshal(body, &loginResp); err != nil {
		return nil, fmt.Errorf("failed to parse response: %w", err)
	}

	// 检查响应状态
	if loginResp.Code != "0" {
		return nil, fmt.Errorf("login failed: %s", loginResp.Message)
	}

	if loginResp.Data == nil {
		return nil, fmt.Errorf("login failed: no data returned")
	}

	return loginResp.Data, nil
}
