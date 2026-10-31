variable "project_name" { type = string }
variable "environment" { type = string }
variable "region" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}
