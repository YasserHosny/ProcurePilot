provider "bunnynet" {
  api_key = var.bunny_api_key
}

locals {
  app_name          = "${var.project_name}-${var.environment}"
  backend_name      = "${var.project_name}-backend"
  frontend_name     = "${var.project_name}-frontend"
  backend_hostname  = "${var.project_name}-api.${var.domain_name}"
  frontend_hostname = var.environment == "production" ? var.domain_name : "${var.environment}.${var.domain_name}"
}

# -----------------------------------------------------------------------------
# Container Image Registry (GHCR)
# -----------------------------------------------------------------------------
resource "bunnynet_compute_container_imageregistry" "ghcr" {
  registry = "GitHub"
  username = var.github_username
  token    = var.github_token
}

# -----------------------------------------------------------------------------
# bunny.net Magic Containers Application
# -----------------------------------------------------------------------------
# A single Bunny Magic Container app hosts both the backend and frontend
# containers within a shared network namespace.
# -----------------------------------------------------------------------------
resource "bunnynet_compute_container_app" "app" {
  name             = local.app_name
  version          = 2
  regions_allowed  = ["DE", "UK", "US"]
  regions_required = ["DE"]

  container {
    name            = local.backend_name
    image_registry  = bunnynet_compute_container_imageregistry.ghcr.id
    image_namespace = var.image_namespace
    image_name      = "procurepilot-api"
    image_tag       = "latest"
  }

  container {
    name            = local.frontend_name
    image_registry  = bunnynet_compute_container_imageregistry.ghcr.id
    image_namespace = var.image_namespace
    image_name      = "procurepilot-web"
    image_tag       = "latest"
  }
}

# -----------------------------------------------------------------------------
# DNS Zone and Records
# -----------------------------------------------------------------------------
resource "bunnynet_dns_zone" "primary" {
  domain = var.domain_name
}

resource "bunnynet_dns_record" "backend" {
  zone  = bunnynet_dns_zone.primary.id
  name  = "${var.project_name}-api"
  type  = "CNAME"
  value = "${local.app_name}.b-cdn.net"
  ttl   = 300
}

resource "bunnynet_dns_record" "frontend" {
  zone  = bunnynet_dns_zone.primary.id
  name  = var.environment == "production" ? "@" : var.environment
  type  = "CNAME"
  value = "${local.app_name}.b-cdn.net"
  ttl   = 300
}
