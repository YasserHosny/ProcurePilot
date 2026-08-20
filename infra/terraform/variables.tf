variable "bunny_api_key" {
  description = "Account API key for bunny.net"
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Deployment environment name (e.g. staging, production)"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Project name identifier used in resource names"
  type        = string
  default     = "procurepilot"
}

variable "domain_name" {
  description = "Apex domain name for DNS and endpoints"
  type        = string
  default     = "procurepilot.com"
}

variable "github_username" {
  description = "GitHub username or organization for container registry access"
  type        = string
  default     = "procurepilot"
}

variable "github_token" {
  description = "GitHub Personal Access Token (or GITHUB_TOKEN) for container registry read access"
  type        = string
  sensitive   = true
  default     = ""
}

variable "image_namespace" {
  description = "Container image namespace/organization on GHCR"
  type        = string
  default     = "procurepilot"
}

variable "backend_port" {
  description = "Port exposed by the backend API container"
  type        = number
  default     = 8000
}

variable "frontend_port" {
  description = "Port exposed by the frontend container"
  type        = number
  default     = 80
}

variable "supabase_url" {
  description = "External URL of the Supabase instance"
  type        = string
  default     = ""
}

variable "supabase_anon_key" {
  description = "Supabase anonymous API key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "supabase_service_role_key" {
  description = "Supabase service role API key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "supabase_jwt_secret" {
  description = "Supabase JWT secret for token verification"
  type        = string
  sensitive   = true
  default     = ""
}
