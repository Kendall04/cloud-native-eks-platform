variable "project_name" {
  description = "Project name used for tagging."
  type        = string
}

variable "environment" {
  description = "Environment name used for tagging."
  type        = string
}

variable "region" {
  description = "AWS region for the deployment."
  type        = string
}

variable "name" {
  description = "Explicit RDS identifier. Defaults to a derived project/environment name."
  type        = string
  default     = null
  nullable    = true
}

variable "engine" {
  description = "Database engine to deploy."
  type        = string
}

variable "engine_version" {
  description = "Database engine version."
  type        = string
}

variable "instance_class" {
  description = "RDS instance class."
  type        = string
}

variable "allocated_storage" {
  description = "Initial allocated storage in GiB."
  type        = number
}

variable "max_allocated_storage" {
  description = "Maximum autoscaled storage in GiB."
  type        = number
  default     = 100
}

variable "storage_type" {
  description = "Storage type for the DB instance."
  type        = string
  default     = "gp3"
}

variable "storage_encrypted" {
  description = "Whether storage encryption is enabled."
  type        = bool
  default     = true
}

variable "database_name" {
  description = "Initial database name."
  type        = string
  default     = null
  nullable    = true
}

variable "username" {
  description = "Master username for the database."
  type        = string
}

variable "password" {
  description = "Master password when manage_master_user_password is false."
  type        = string
  default     = null
  nullable    = true
  sensitive   = true

  validation {
    condition     = var.manage_master_user_password || var.password != null
    error_message = "password must be set when manage_master_user_password is false."
  }
}

variable "manage_master_user_password" {
  description = "Whether RDS manages the master password in Secrets Manager."
  type        = bool
  default     = true
}

variable "port" {
  description = "Database port."
  type        = number
  default     = 5432
}

variable "subnet_ids" {
  description = "Private subnet IDs used by the DB subnet group."
  type        = list(string)
}

variable "vpc_id" {
  description = "VPC ID where the DB instance is deployed."
  type        = string
}

variable "allowed_cidr_blocks" {
  description = "CIDR ranges allowed to connect to the database."
  type        = list(string)
  default     = []
}

variable "allowed_security_group_ids" {
  description = "Security groups allowed to connect to the database."
  type        = list(string)
  default     = []
}

variable "publicly_accessible" {
  description = "Whether the DB instance should receive a public endpoint."
  type        = bool
  default     = false
}

variable "multi_az" {
  description = "Whether to deploy the DB instance across multiple AZs."
  type        = bool
  default     = false
}

variable "backup_retention_period" {
  description = "Number of days to retain automated backups."
  type        = number
  default     = 7
}

variable "backup_window" {
  description = "Preferred backup window."
  type        = string
  default     = null
  nullable    = true
}

variable "maintenance_window" {
  description = "Preferred maintenance window."
  type        = string
  default     = null
  nullable    = true
}

variable "apply_immediately" {
  description = "Whether modifications are applied immediately."
  type        = bool
  default     = false
}

variable "performance_insights_enabled" {
  description = "Whether Performance Insights is enabled."
  type        = bool
  default     = true
}

variable "deletion_protection" {
  description = "Whether deletion protection is enabled."
  type        = bool
  default     = true
}

variable "skip_final_snapshot" {
  description = "Whether to skip the final snapshot on deletion."
  type        = bool
  default     = false
}

variable "final_snapshot_identifier" {
  description = "Identifier for the final snapshot when skip_final_snapshot is false."
  type        = string
  default     = null
  nullable    = true
}

variable "enabled_cloudwatch_logs_exports" {
  description = "Database logs exported to CloudWatch."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Additional tags applied to created resources."
  type        = map(string)
  default     = {}
}

variable "teardown" {
  description = "Reviewed teardown only. Null preserves normal runtime protection."
  type = object({
    decision                  = string
    final_snapshot_identifier = optional(string)
    delete_automated_backups  = bool
  })
  default = null
  validation {
    condition = var.teardown == null ? true : (
      contains(["KEEP_FINAL_SNAPSHOT", "PURGE_DATABASE_EVIDENCE"], var.teardown.decision) &&
      var.teardown.delete_automated_backups &&
      (var.teardown.decision == "KEEP_FINAL_SNAPSHOT" ?
        try(can(regex("^[a-z][a-z0-9-]{0,254}$", var.teardown.final_snapshot_identifier)) &&
          !strcontains(var.teardown.final_snapshot_identifier, "--") &&
          !endswith(var.teardown.final_snapshot_identifier, "-") &&
        var.teardown.final_snapshot_identifier != "${coalesce(var.name, "${var.project_name}-${var.environment}-db")}-final", false) :
      var.teardown.final_snapshot_identifier == null)
    )
    error_message = "Teardown requires an explicit KEEP/PURGE decision, backups purge and a unique KEEP snapshot identifier."
  }
}

