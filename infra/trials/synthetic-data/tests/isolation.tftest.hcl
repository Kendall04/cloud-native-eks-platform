# Local plan tests only. All f-prefixed IDs below are fixtures, never observed
# future resources. Protected IDs occur only in rejection cases. No SDK effects.
mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{}" }
  }
}

variables {
  bindings = {
    vpc_id                      = "vpc-f1f1f1f1f1f1f1f11"
    private_subnet_ids          = ["subnet-f2f2f2f2f2f2f2f22", "subnet-f3f3f3f3f3f3f3f33"]
    workload_security_group_ids = ["sg-f4f4f4f4f4f4f4f44"]
    event_kms_key_arn           = "arn:aws:kms:us-east-1:341936017254:key/ffffffff-ffff-4fff-8fff-ffffffffffff"
  }
}

run "isolated_data_graph" {
  command = plan

  assert {
    condition     = output.synthetic_data.dataClass == "SYNTHETIC_ONLY" && can(regex("^cnp-trial-[0-9a-f]{32}-postgres$", output.synthetic_data.database.identifier))
    error_message = "Only the UUID-bound synthetic database may feed data outputs."
  }
  assert {
    condition     = length(output.synthetic_data.secretArns) == 10 && length(output.synthetic_data.queueArns) == 2 && length(output.synthetic_data.consumerDlqArns) == 1
    error_message = "The data graph must keep ten new secret containers and three distinct queues."
  }
  assert {
    condition     = startswith(output.synthetic_data.eventBus.name, "cnp-trial-") && endswith(output.synthetic_data.eventBus.name, "-bus")
    error_message = "The event bus must use the isolated namespace."
  }
}

run "reject_protected_vpc" {
  command = plan
  variables {
    bindings = {
      vpc_id                      = "vpc-05a8ec8d7de5a8271"
      private_subnet_ids          = ["subnet-f2f2f2f2f2f2f2f22", "subnet-f3f3f3f3f3f3f3f33"]
      workload_security_group_ids = ["sg-f4f4f4f4f4f4f4f44"]
      event_kms_key_arn           = "arn:aws:kms:us-east-1:341936017254:key/ffffffff-ffff-4fff-8fff-ffffffffffff"
    }
  }
  expect_failures = [var.bindings]
}

run "reject_protected_subnet" {
  command = plan
  variables {
    bindings = {
      vpc_id                      = "vpc-f1f1f1f1f1f1f1f11"
      private_subnet_ids          = ["subnet-046105462ce63d6e2", "subnet-f3f3f3f3f3f3f3f33"]
      workload_security_group_ids = ["sg-f4f4f4f4f4f4f4f44"]
      event_kms_key_arn           = "arn:aws:kms:us-east-1:341936017254:key/ffffffff-ffff-4fff-8fff-ffffffffffff"
    }
  }
  expect_failures = [var.bindings]
}

run "reject_protected_db_security_group" {
  command = plan
  variables {
    bindings = {
      vpc_id                      = "vpc-f1f1f1f1f1f1f1f11"
      private_subnet_ids          = ["subnet-f2f2f2f2f2f2f2f22", "subnet-f3f3f3f3f3f3f3f33"]
      workload_security_group_ids = ["sg-0c778ed332607ae02"]
      event_kms_key_arn           = "arn:aws:kms:us-east-1:341936017254:key/ffffffff-ffff-4fff-8fff-ffffffffffff"
    }
  }
  expect_failures = [var.bindings]
}

run "reject_protected_event_key" {
  command = plan
  variables {
    bindings = {
      vpc_id                      = "vpc-f1f1f1f1f1f1f1f11"
      private_subnet_ids          = ["subnet-f2f2f2f2f2f2f2f22", "subnet-f3f3f3f3f3f3f3f33"]
      workload_security_group_ids = ["sg-f4f4f4f4f4f4f4f44"]
      event_kms_key_arn           = "arn:aws:kms:us-east-1:341936017254:key/88e09005-a830-4f4f-90e3-493fe721272f"
    }
  }
  expect_failures = [var.bindings]
}
