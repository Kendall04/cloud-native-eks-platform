variable "name_prefix" { type = string }
variable "vpc_id" { type = string }
variable "public_subnet_id" { type = string }
variable "availability_zone" { type = string }
variable "instance_type" { type = string }
variable "ami_id" {
  description = "Explicit NAT AMI ID; null selects the latest official Amazon Linux 2023 image."
  type        = string
  default     = null

  validation {
    condition     = var.ami_id == null || can(regex("^ami-([0-9a-f]{8}|[0-9a-f]{17})$", var.ami_id))
    error_message = "ami_id must be null or a valid EC2 AMI ID."
  }
}
variable "key_name" {
  type     = string
  default  = null
  nullable = true
}
variable "allowed_ssh_cidr" { type = string }
variable "private_subnet_cidr" {
  type     = string
  default  = null
  nullable = true
}
variable "private_subnet_cidrs" {
  type    = list(string)
  default = []
}
variable "enable_ssm" { type = bool }
variable "tags" { type = map(string) }
