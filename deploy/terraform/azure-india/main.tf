terraform {
  required_version = ">= 1.6"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.90"
    }
  }
  backend "azurerm" {
    # Populated at init: -backend-config=backend.hcl
    # resource_group_name  = "opex-tfstate-rg"
    # storage_account_name = "opextfstate<suffix>"
    # container_name       = "tfstate"
    # key                  = "opex-analyzer.terraform.tfstate"
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
}

data "azurerm_client_config" "current" {}

locals {
  tags = {
    "opex-engagement-id" = var.engagement_id
    "opex-product"       = "opex-intelligence-platform"
    "opex-environment"   = var.environment
    "opex-managed-by"    = "terraform"
  }
}

# ── Resource Group ────────────────────────────────────────────────────────────
resource "azurerm_resource_group" "opex" {
  name     = "opex-${var.engagement_id}-rg"
  location = var.azure_region
  tags     = local.tags
}

# ── Virtual Network ───────────────────────────────────────────────────────────
resource "azurerm_virtual_network" "opex" {
  name                = "opex-${var.engagement_id}-vnet"
  resource_group_name = azurerm_resource_group.opex.name
  location            = azurerm_resource_group.opex.location
  address_space       = [var.vnet_cidr]
  tags                = local.tags
}

resource "azurerm_subnet" "app" {
  name                 = "app-subnet"
  resource_group_name  = azurerm_resource_group.opex.name
  virtual_network_name = azurerm_virtual_network.opex.name
  address_prefixes     = [var.app_subnet_cidr]
  delegation {
    name = "aci-delegation"
    service_delegation {
      name    = "Microsoft.ContainerInstance/containerGroups"
      actions = ["Microsoft.Network/virtualNetworks/subnets/action"]
    }
  }
}

resource "azurerm_subnet" "data" {
  name                 = "data-subnet"
  resource_group_name  = azurerm_resource_group.opex.name
  virtual_network_name = azurerm_virtual_network.opex.name
  address_prefixes     = [var.data_subnet_cidr]
}

# ── Azure Key Vault (client KMS) ──────────────────────────────────────────────
resource "azurerm_key_vault" "opex" {
  name                       = "opex-kv-${substr(var.engagement_id, 0, 14)}"
  resource_group_name        = azurerm_resource_group.opex.name
  location                   = azurerm_resource_group.opex.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "premium"
  soft_delete_retention_days = 90
  purge_protection_enabled   = true
  tags                       = local.tags

  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id
    key_permissions     = ["Create", "Get", "List", "Rotate", "Delete", "Purge"]
    secret_permissions  = ["Set", "Get", "List", "Delete", "Purge"]
  }
}

resource "azurerm_key_vault_key" "opex_data" {
  name         = "opex-data-key"
  key_vault_id = azurerm_key_vault.opex.id
  key_type     = "RSA"
  key_size     = 4096
  key_opts     = ["decrypt", "encrypt", "wrapKey", "unwrapKey"]
  rotation_policy {
    automatic {
      time_before_expiry = "P30D"
    }
    expire_after         = "P365D"
    notify_before_expiry = "P30D"
  }
}

# ── Storage Account (artefacts + backups) ─────────────────────────────────────
resource "azurerm_storage_account" "opex" {
  name                     = "opex${replace(var.engagement_id, "-", "")}sa"
  resource_group_name      = azurerm_resource_group.opex.name
  location                 = azurerm_resource_group.opex.location
  account_tier             = "Standard"
  account_replication_type = "ZRS"
  min_tls_version          = "TLS1_2"
  tags                     = local.tags

  blob_properties {
    versioning_enabled  = true
    delete_retention_policy { days = 14 }
  }

  customer_managed_key {
    key_vault_key_id          = azurerm_key_vault_key.opex_data.id
    user_assigned_identity_id = azurerm_user_assigned_identity.opex.id
  }
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.opex.id]
  }
}

resource "azurerm_storage_container" "artefacts" {
  name                  = "artefacts"
  storage_account_name  = azurerm_storage_account.opex.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "backups" {
  name                  = "backups"
  storage_account_name  = azurerm_storage_account.opex.name
  container_access_type = "private"
}

# ── Managed Identity ──────────────────────────────────────────────────────────
resource "azurerm_user_assigned_identity" "opex" {
  name                = "opex-${var.engagement_id}-identity"
  resource_group_name = azurerm_resource_group.opex.name
  location            = azurerm_resource_group.opex.location
  tags                = local.tags
}

# ── Azure Cache for Redis ─────────────────────────────────────────────────────
resource "azurerm_redis_cache" "opex" {
  name                = "opex-redis-${substr(var.engagement_id, 0, 16)}"
  resource_group_name = azurerm_resource_group.opex.name
  location            = azurerm_resource_group.opex.location
  capacity            = 1
  family              = "C"
  sku_name            = "Standard"
  enable_non_ssl_port = false
  minimum_tls_version = "1.2"
  tags                = local.tags
}

# ── Azure Container Apps (opex-api) ──────────────────────────────────────────
resource "azurerm_container_app_environment" "opex" {
  name                = "opex-${var.engagement_id}-cae"
  resource_group_name = azurerm_resource_group.opex.name
  location            = azurerm_resource_group.opex.location
  tags                = local.tags
}

resource "azurerm_container_app" "opex_api" {
  name                         = "opex-api"
  container_app_environment_id = azurerm_container_app_environment.opex.id
  resource_group_name          = azurerm_resource_group.opex.name
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.opex.id]
  }

  template {
    min_replicas = 1
    max_replicas = var.max_replicas
    container {
      name   = "opex-api"
      image  = var.container_image
      cpu    = var.container_cpu
      memory = var.container_memory
      env {
        name  = "ENGAGEMENT_ID"
        value = var.engagement_id
      }
      env {
        name  = "REDIS_URL"
        value = "rediss://:${azurerm_redis_cache.opex.primary_access_key}@${azurerm_redis_cache.opex.hostname}:6380/0"
      }
    }
  }

  ingress {
    external_enabled = false
    target_port      = 8000
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}
