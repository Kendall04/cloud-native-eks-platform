# Pure mocked-provider test. No RDS account/API, credentials, secret or real DB.
mock_provider "aws" {
  mock_resource "aws_db_instance" {
    defaults = { id = "db-OFFLINE-EKS-GENERATION", resource_id = "db-OFFLINE-EKS-GENERATION" }
  }
}
variables {
  project_name      = "cloud-native-platform"
  environment       = "dev"
  region            = "us-east-1"
  name              = "cloud-native-platform-dev-postgres"
  engine            = "postgres"
  engine_version    = "15.18"
  instance_class    = "db.t4g.micro"
  allocated_storage = 20
  username          = "platform_admin"
  vpc_id            = "vpc-offline-fixture"
  subnet_ids        = ["subnet-offline-a", "subnet-offline-b"]
}
run "protected_runtime" {
  command = apply
  assert {
    condition     = aws_db_instance.this.deletion_protection && !aws_db_instance.this.skip_final_snapshot && aws_db_instance.this.backup_retention_period == 7
    error_message = "Runtime defaults must retain protection, backups and final snapshot."
  }
}
run "same_synthetic_db_retirement_plan" {
  command = plan
  variables {
    teardown = { decision = "PURGE_DATABASE_EVIDENCE", final_snapshot_identifier = null, delete_automated_backups = true }
  }
  assert {
    condition     = aws_db_instance.this.id == "db-OFFLINE-EKS-GENERATION" && aws_db_instance.this.identifier == run.protected_runtime.db_instance_id
    error_message = "Plan must address the same DB generation and identifier."
  }
  assert {
    condition     = !aws_db_instance.this.deletion_protection && aws_db_instance.this.skip_final_snapshot && aws_db_instance.this.delete_automated_backups && aws_db_instance.this.backup_retention_period == 7 && aws_db_instance.this.apply_immediately == false
    error_message = "Only the existing teardown contract changes; runtime backup settings remain."
  }
}
run "reject_ambiguous_purge_snapshot" {
  command = plan
  variables {
    teardown = { decision = "PURGE_DATABASE_EVIDENCE", final_snapshot_identifier = "unexpected-snapshot", delete_automated_backups = true }
  }
  expect_failures = [var.teardown]
}
