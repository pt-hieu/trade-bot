terraform {
  required_version = ">= 1.0"

  # Partial backend config. Supply your own bucket/region/profile at init time:
  #   terraform init -backend-config=backend.hcl
  backend "s3" {
    key     = "infra/terraform.tfstate"
    encrypt = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region  = "ap-southeast-1" # Singapore (closest to Vietnam)
  profile = var.aws_profile
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# SSH Key Pair
resource "aws_lightsail_key_pair" "vnstock" {
  name       = "vnstock-api-key"
  public_key = var.ssh_public_key
}

# Lightsail Instance
resource "aws_lightsail_instance" "vnstock_api" {
  name              = "vnstock-api"
  availability_zone = "ap-southeast-1a"
  blueprint_id      = "ubuntu_24_04"
  bundle_id         = "nano_3_0" # $3.50/mo: 512MB, 1vCPU, 20GB SSD
  key_pair_name     = aws_lightsail_key_pair.vnstock.name

  tags = {
    Project = "swingy"
  }
}

# Static IP
resource "aws_lightsail_static_ip" "vnstock_api" {
  name = "vnstock-api-ip"
}

# Attach static IP to instance
resource "aws_lightsail_static_ip_attachment" "vnstock_api" {
  static_ip_name = aws_lightsail_static_ip.vnstock_api.name
  instance_name  = aws_lightsail_instance.vnstock_api.name
}

# Firewall rules
resource "aws_lightsail_instance_public_ports" "vnstock_api" {
  instance_name = aws_lightsail_instance.vnstock_api.name

  # SSH is restricted to the operator's own address, not the whole internet.
  port_info {
    protocol  = "tcp"
    from_port = 22
    to_port   = 22
    cidrs     = var.ssh_allowed_cidrs
  }

  port_info {
    protocol  = "tcp"
    from_port = 80
    to_port   = 80
  }

  port_info {
    protocol  = "tcp"
    from_port = 443
    to_port   = 443
  }

  # 8000 (vnstock-api) and 8001 (mcp-server) stay closed at the firewall.
  # Caddy terminates TLS on 443 and reverse-proxies to them over loopback.
}

# DNS record for finance.example.com
resource "cloudflare_record" "finance" {
  zone_id = var.cloudflare_zone_id
  name    = "finance"
  content = aws_lightsail_static_ip.vnstock_api.ip_address
  type    = "A"
  # DNS-only exposes the origin IP directly. Set to true to put Cloudflare in front and
  # hide it; Caddy still terminates TLS behind the proxy.
  proxied = var.cloudflare_proxied
}

# DNS for the dashboard subdomain is managed by Cloudflare Workers custom_domain
# (configured in web/wrangler.jsonc, not Terraform)
