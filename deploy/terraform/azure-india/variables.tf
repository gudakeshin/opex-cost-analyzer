variable "azure_region" {
  description = "Azure region — Central India for data residency"
  type        = string
  default     = "centralindia"
}

variable "engagement_id" {
  description = "Unique engagement identifier"
  type        = string
}

variable "environment" {
  type    = string
  default = "production"
}

variable "vnet_cidr" {
  type    = string
  default = "10.1.0.0/16"
}

variable "app_subnet_cidr" {
  type    = string
  default = "10.1.1.0/24"
}

variable "data_subnet_cidr" {
  type    = string
  default = "10.1.2.0/24"
}

variable "container_image" {
  description = "ACR image URI for the opex-api container"
  type        = string
}

variable "container_cpu" {
  type    = number
  default = 2.0
}

variable "container_memory" {
  type    = string
  default = "4Gi"
}

variable "max_replicas" {
  type    = number
  default = 5
}
