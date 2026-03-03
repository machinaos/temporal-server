package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"time"

	"go.temporal.io/server/common/authorization"
	"go.temporal.io/server/common/cluster"
	"go.temporal.io/server/common/config"
	"go.temporal.io/server/common/dynamicconfig"
	tlog "go.temporal.io/server/common/log"
	"go.temporal.io/server/common/metrics"
	sqliteplugin "go.temporal.io/server/common/persistence/sql/sqlplugin/sqlite"
	"go.temporal.io/server/schema/sqlite"
	"go.temporal.io/server/temporal"
)

// ServiceConfig holds per-service port configuration.
type ServiceConfig struct {
	GRPCPort       int `json:"grpcPort"`
	HTTPPort       int `json:"httpPort,omitempty"`
	MembershipPort int `json:"membershipPort"`
}

// ServerSettings holds top-level server settings.
type ServerSettings struct {
	BroadcastAddress string `json:"broadcastAddress"`
	LogLevel         string `json:"logLevel"`
}

// PersistenceSettings holds database configuration.
type PersistenceSettings struct {
	DBPath           string `json:"dbPath"`
	NumHistoryShards int32  `json:"numHistoryShards"`
}

// MetricsSettings holds metrics endpoint configuration.
type MetricsSettings struct {
	Enabled bool   `json:"enabled"`
	Port    int    `json:"port"`
	Path    string `json:"path"`
}

// PProfSettings holds pprof debug endpoint configuration.
type PProfSettings struct {
	Enabled bool `json:"enabled"`
	Port    int  `json:"port"`
}

// AppConfig is the top-level JSON config schema.
type AppConfig struct {
	Server      ServerSettings              `json:"server"`
	Persistence PersistenceSettings         `json:"persistence"`
	Services    map[string]ServiceConfig    `json:"services"`
	Metrics     MetricsSettings             `json:"metrics"`
	PProf       PProfSettings               `json:"pprof"`
	Namespaces  []string                    `json:"namespaces"`
}

func main() {
	configPath := flag.String("config", "config.json", "path to JSON config file")
	flag.Parse()

	appCfg, err := loadConfig(*configPath)
	if err != nil {
		log.Fatalf("Failed to load config from %s: %v", *configPath, err)
	}

	// Resolve relative dbPath against CWD (project root)
	dbPath := appCfg.Persistence.DBPath
	dbPath, _ = filepath.Abs(dbPath)

	// Allow env var override
	if envPath := os.Getenv("TEMPORAL_DB_PATH"); envPath != "" {
		dbPath = envPath
	}

	frontendSvc := appCfg.Services["frontend"]
	log.Printf("Temporal custom server (SQLite)")
	log.Printf("  Config:   %s", *configPath)
	log.Printf("  Database: %s", dbPath)
	log.Printf("  gRPC:     %s:%d", appCfg.Server.BroadcastAddress, frontendSvc.GRPCPort)
	if frontendSvc.HTTPPort > 0 {
		log.Printf("  HTTP/UI:  %s:%d", appCfg.Server.BroadcastAddress, frontendSvc.HTTPPort)
	}
	if appCfg.Metrics.Enabled {
		log.Printf("  Metrics:  %s:%d%s", appCfg.Server.BroadcastAddress, appCfg.Metrics.Port, appCfg.Metrics.Path)
	}

	// Build SQLite persistence config (follows lite_server.go pattern)
	sqliteConfig := config.SQL{
		PluginName:   sqliteplugin.PluginName,
		DatabaseName: dbPath,
		ConnectAttributes: map[string]string{
			"mode": "rwc",
		},
	}

	// Run schema setup if database file does not exist yet
	if _, err := os.Stat(dbPath); os.IsNotExist(err) {
		dir := filepath.Dir(dbPath)
		if err := os.MkdirAll(dir, 0755); err != nil {
			log.Fatalf("Failed to create data directory %s: %v", dir, err)
		}
		log.Printf("New database -- running schema setup...")
		if err := sqlite.SetupSchema(&sqliteConfig); err != nil {
			log.Fatalf("Schema setup failed: %v", err)
		}
		log.Printf("Schema setup complete.")
	}

	// Pre-create configured namespaces
	for _, ns := range appCfg.Namespaces {
		nsConfig, err := sqlite.NewNamespaceConfig("active", ns, false, nil)
		if err != nil {
			log.Fatalf("Failed to build namespace config for %q: %v", ns, err)
		}
		if err := sqlite.CreateNamespaces(&sqliteConfig, nsConfig); err != nil {
			log.Printf("Namespace %q (may already exist): %v", ns, err)
		}
	}

	// Build full Temporal server config from our JSON config
	temporalCfg := buildTemporalConfig(appCfg, &sqliteConfig, dbPath)

	// Logger
	logger := tlog.NewZapLogger(tlog.BuildZapLogger(tlog.Config{
		Stdout: true,
		Level:  appCfg.Server.LogLevel,
	}))

	// Authorization (default no-op from config)
	auth, err := authorization.GetAuthorizerFromConfig(&temporalCfg.Global.Authorization)
	if err != nil {
		log.Fatalf("Failed to create authorizer: %v", err)
	}
	claimMapper, err := authorization.GetClaimMapperFromConfig(&temporalCfg.Global.Authorization, logger)
	if err != nil {
		log.Fatalf("Failed to create claim mapper: %v", err)
	}

	// Create Temporal server
	srv, err := temporal.NewServer(
		temporal.ForServices(temporal.DefaultServices),
		temporal.WithConfig(temporalCfg),
		temporal.WithLogger(logger),
		temporal.WithAuthorizer(auth),
		temporal.WithClaimMapper(func(c *config.Config) authorization.ClaimMapper {
			return claimMapper
		}),
		temporal.WithDynamicConfigClient(dynamicconfig.StaticClient{}),
		temporal.InterruptOn(temporal.InterruptCh()),
	)
	if err != nil {
		log.Fatalf("Failed to create Temporal server: %v", err)
	}

	log.Printf("Starting Temporal server...")
	if err := srv.Start(); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
	log.Printf("Temporal server stopped.")
}

func loadConfig(path string) (*AppConfig, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read file: %w", err)
	}
	var cfg AppConfig
	if err := json.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("parse json: %w", err)
	}

	// Defaults
	if cfg.Server.BroadcastAddress == "" {
		cfg.Server.BroadcastAddress = "127.0.0.1"
	}
	if cfg.Server.LogLevel == "" {
		cfg.Server.LogLevel = "info"
	}
	if cfg.Persistence.NumHistoryShards == 0 {
		cfg.Persistence.NumHistoryShards = 1
	}
	if cfg.Metrics.Path == "" {
		cfg.Metrics.Path = "/metrics"
	}

	// Validate required fields
	if cfg.Persistence.DBPath == "" {
		return nil, fmt.Errorf("persistence.dbPath is required")
	}
	if _, ok := cfg.Services["frontend"]; !ok {
		return nil, fmt.Errorf("services.frontend is required")
	}
	for _, name := range []string{"frontend", "history", "matching", "worker"} {
		svc, ok := cfg.Services[name]
		if !ok {
			return nil, fmt.Errorf("services.%s is required", name)
		}
		if svc.GRPCPort == 0 {
			return nil, fmt.Errorf("services.%s.grpcPort is required", name)
		}
		if svc.MembershipPort == 0 {
			return nil, fmt.Errorf("services.%s.membershipPort is required", name)
		}
	}

	return &cfg, nil
}

func buildTemporalConfig(appCfg *AppConfig, sqliteConfig *config.SQL, dbPath string) *config.Config {
	addr := appCfg.Server.BroadcastAddress
	frontendSvc := appCfg.Services["frontend"]
	frontendAddr := fmt.Sprintf("%s:%d", addr, frontendSvc.GRPCPort)

	cfg := &config.Config{
		Global: config.Global{
			Membership: config.Membership{
				MaxJoinDuration:  30 * time.Second,
				BroadcastAddress: addr,
			},
		},
		Persistence: config.Persistence{
			DefaultStore:     sqliteplugin.PluginName,
			VisibilityStore:  sqliteplugin.PluginName,
			NumHistoryShards: appCfg.Persistence.NumHistoryShards,
			DataStores: map[string]config.DataStore{
				sqliteplugin.PluginName: {SQL: sqliteConfig},
			},
		},
		ClusterMetadata: &cluster.Config{
			EnableGlobalNamespace:    false,
			FailoverVersionIncrement: 10,
			MasterClusterName:        "active",
			CurrentClusterName:       "active",
			ClusterInformation: map[string]cluster.ClusterInformation{
				"active": {
					Enabled:                true,
					InitialFailoverVersion: 1,
					RPCAddress:             frontendAddr,
				},
			},
		},
		DCRedirectionPolicy: config.DCRedirectionPolicy{
			Policy: "noop",
		},
		Archival: config.Archival{
			History:    config.HistoryArchival{State: "disabled", EnableRead: false},
			Visibility: config.VisibilityArchival{State: "disabled", EnableRead: false},
		},
		NamespaceDefaults: config.NamespaceDefaults{
			Archival: config.ArchivalNamespaceDefaults{
				History:    config.HistoryArchivalNamespaceDefaults{State: "disabled"},
				Visibility: config.VisibilityArchivalNamespaceDefaults{State: "disabled"},
			},
		},
		PublicClient: config.PublicClient{
			HostPort: frontendAddr,
		},
	}

	// Build service configs from JSON
	cfg.Services = make(map[string]config.Service)
	for name, svcCfg := range appCfg.Services {
		svc := config.Service{
			RPC: config.RPC{
				GRPCPort:        svcCfg.GRPCPort,
				MembershipPort:  svcCfg.MembershipPort,
				BindOnLocalHost: true,
			},
		}
		if svcCfg.HTTPPort > 0 {
			svc.RPC.HTTPPort = svcCfg.HTTPPort
		}
		cfg.Services[name] = svc
	}

	// Metrics
	if appCfg.Metrics.Enabled && appCfg.Metrics.Port > 0 {
		cfg.Global.Metrics = &metrics.Config{
			Prometheus: &metrics.PrometheusConfig{
				ListenAddress: fmt.Sprintf("%s:%d", addr, appCfg.Metrics.Port),
				HandlerPath:   appCfg.Metrics.Path,
			},
		}
	}

	// PProf
	if appCfg.PProf.Enabled && appCfg.PProf.Port > 0 {
		cfg.Global.PProf = config.PProf{Port: appCfg.PProf.Port}
	}

	return cfg
}
