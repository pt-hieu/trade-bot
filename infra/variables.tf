variable "ssh_public_key" {
  description = "SSH public key for instance access"
  type        = string
}

variable "aws_profile" {
  description = "AWS CLI profile to use"
  type        = string
  default     = "swingy"
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token with Zone:DNS:Edit permission for example.com"
  type        = string
  sensitive   = true
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for example.com"
  type        = string
}

variable "ssh_allowed_cidrs" {
  description = "CIDRs allowed to reach SSH. No default on purpose — set it to your own address."
  type        = list(string)
}

variable "cloudflare_proxied" {
  description = <<-EOT
    Route the API subdomain through Cloudflare's proxy. Defaults to false, which is the
    configuration this stack is known to work with: Caddy on the origin gets direct
    traffic and can complete ACME challenges. Setting it to true hides the origin IP but
    requires you to also pick a compatible Cloudflare SSL mode and certificate strategy.
  EOT
  type        = bool
  default     = false
}
