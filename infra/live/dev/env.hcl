locals {
  project_name                  = "cloud-native-platform"
  environment                   = "dev"
  region                        = "us-east-1"
  eks_cluster_name              = "logistics-platform-dev"
  nat_mode                      = "instance"
  nat_instance_type             = "t3.micro"
  nat_instance_key_name         = null
  nat_instance_allowed_ssh_cidr = "127.0.0.1/32"
  nat_instance_enable_ssm       = true
  nat_recovery_enabled          = false # Separate reviewed activation; zero ASG capacity while paused.
  enable_apigateway_integration = true
  jwt_issuer                    = "logistics-platform"
  jwt_audience                  = "logistics-platform-clients"
  platform_database_name        = "platform"

  # CV-READY: notification disabled (no live stack); analytics out of scope.
  tags = {
    Repository = "cloud-native-platform-eks"
    ManagedBy  = "Terraform"
    Owner      = "platform-team"
  }
}
