output "app_id" {
  description = "The ID of the bunny.net Magic Container application"
  value       = bunnynet_compute_container_app.app.id
}

output "dns_zone_id" {
  description = "The ID of the bunny.net DNS zone"
  value       = bunnynet_dns_zone.primary.id
}

output "backend_hostname" {
  description = "Public hostname for the backend API"
  value       = local.backend_hostname
}

output "frontend_hostname" {
  description = "Public hostname for the frontend web application"
  value       = local.frontend_hostname
}
