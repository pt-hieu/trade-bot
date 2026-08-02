output "instance_name" {
  value       = aws_lightsail_instance.vnstock_api.name
  description = "Lightsail instance name"
}

output "static_ip" {
  value       = aws_lightsail_static_ip.vnstock_api.ip_address
  description = "Static IP address for the vnstock API server"
}

output "ssh_command" {
  value       = "ssh -i ~/.ssh/vnstock-api ubuntu@${aws_lightsail_static_ip.vnstock_api.ip_address}"
  description = "SSH command to connect to the instance"
}

output "finance_url" {
  value       = "https://${cloudflare_record.finance.hostname}"
  description = "HTTPS URL for finance services (vnstock API + MCP)"
}

# swingy_web_url: https://swingy.example.com (managed by Wrangler custom_domain)
