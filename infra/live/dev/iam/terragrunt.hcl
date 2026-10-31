include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

locals {
  env_config                         = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  project_name                       = local.env_config.locals.project_name
  environment                        = local.env_config.locals.environment
  shipment_service_account_namespace = "apps"
  shipment_service_account_name      = "shipment-service"
  tracking_service_account_namespace = "apps"
  tracking_service_account_name      = "tracking-service"
  shipment_queue_name                = "${local.project_name}-${local.environment}-shipment-events-queue"
}

terraform {
  source = "../../../modules/iam"
}

dependency "eks" {
  config_path = "../eks"

  mock_outputs = {
    oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/EXAMPLE"
    oidc_provider_url = "https://oidc.eks.us-east-1.amazonaws.com/id/EXAMPLE"
  }

  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

dependency "sqs" {
  config_path = "../sqs"

  mock_outputs = {
    queue_arns = {
      "${local.shipment_queue_name}" = "arn:aws:sqs:us-east-1:123456789012:${local.shipment_queue_name}"
    }
  }

  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

dependency "eventbridge" {
  config_path = "../eventbridge"

  mock_outputs = {
    event_bus_arn = "arn:aws:events:us-east-1:123456789012:event-bus/${local.project_name}-${local.environment}-bus"
  }

  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

dependency "event_encryption" {
  config_path = "../event-encryption"
  mock_outputs = {
    key_arn = "arn:aws:kms:us-east-1:123456789012:key/00000000-0000-0000-0000-000000000000"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

dependency "retained_runtime" {
  config_path = "../runtime-secrets"
}

inputs = {
  roles = {
    "${local.project_name}-${local.environment}-external-secrets-cert-irsa" = {
      permissions_boundary = "arn:aws:iam::${get_aws_account_id()}:policy/cnp-cert-app-workload-boundary"
      description          = "Temporary certification ESO; retained historical role remains unchanged."
      max_session_duration = 3600
      tags                 = { Owner = "Kendall", Purpose = "eks-certification-temporary-eso" }
      assume_role_policy = jsonencode({
        Version = "2012-10-17"
        Statement = [{
          Effect    = "Allow", Action = "sts:AssumeRoleWithWebIdentity"
          Principal = { Federated = dependency.eks.outputs.oidc_provider_arn }
          Condition = { StringEquals = {
            "${replace(dependency.eks.outputs.oidc_provider_url, "https://", "")}:aud" = "sts.amazonaws.com"
            "${replace(dependency.eks.outputs.oidc_provider_url, "https://", "")}:sub" = "system:serviceaccount:kube-system:external-secrets"
          } }
        }]
      })
      inline_policies = {
        eso-retained-ten-read = jsonencode({
          Version = "2012-10-17"
          Statement = [{
            Effect   = "Allow"
            Action   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
            Resource = [for name in ["auth-runtime-db", "auth-migration-db", "shipment-runtime-db", "shipment-migration-db", "tracking-runtime-db", "tracking-migration-db", "internal-trust", "bootstrap-admin", "auth-jwt", "gateway-trust"] : dependency.retained_runtime.outputs.secret_arns[name]]
          }]
        })
      }
    }
    "${local.project_name}-${local.environment}-keda-irsa" = {
      permissions_boundary = "arn:aws:iam::${get_aws_account_id()}:policy/cnp-cert-app-workload-boundary"
      description          = "KEDA metrics only; no message consumption or decryption."
      assume_role_policy = jsonencode({
        Version = "2012-10-17"
        Statement = [{
          Effect    = "Allow"
          Action    = "sts:AssumeRoleWithWebIdentity"
          Principal = { Federated = dependency.eks.outputs.oidc_provider_arn }
          Condition = { StringEquals = {
            "${replace(dependency.eks.outputs.oidc_provider_url, "https://", "")}:aud" = "sts.amazonaws.com"
            "${replace(dependency.eks.outputs.oidc_provider_url, "https://", "")}:sub" = "system:serviceaccount:kube-system:keda-operator"
          } }
        }]
      })
      inline_policies = {
        queue-metrics = jsonencode({
          Version = "2012-10-17"
          Statement = [{
            Effect   = "Allow"
            Action   = ["sqs:GetQueueAttributes"]
            Resource = dependency.sqs.outputs.queue_arns[local.shipment_queue_name]
          }]
        })
      }
    }
    "${local.project_name}-${local.environment}-shipment-service-irsa" = {
      permissions_boundary = "arn:aws:iam::${get_aws_account_id()}:policy/cnp-cert-app-workload-boundary"
      description          = "IRSA role for shipment-service running on EKS."
      assume_role_policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
          {
            Effect = "Allow"
            Action = "sts:AssumeRoleWithWebIdentity"
            Principal = {
              Federated = dependency.eks.outputs.oidc_provider_arn
            }
            Condition = {
              StringEquals = {
                "${replace(dependency.eks.outputs.oidc_provider_url, "https://", "")}:aud" = "sts.amazonaws.com"
                "${replace(dependency.eks.outputs.oidc_provider_url, "https://", "")}:sub" = "system:serviceaccount:${local.shipment_service_account_namespace}:${local.shipment_service_account_name}"
              }
            }
          }
        ]
      })
      inline_policies = {
        shipment-service = jsonencode({
          Version = "2012-10-17"
          Statement = [
            {
              Effect = "Allow"
              Action = [
                "sqs:ReceiveMessage",
                "sqs:DeleteMessage",
                "sqs:GetQueueAttributes",
                "sqs:ChangeMessageVisibility"
              ]
              Resource = dependency.sqs.outputs.queue_arns[local.shipment_queue_name]
            },
            {
              Effect   = "Allow"
              Action   = ["kms:Decrypt"]
              Resource = dependency.event_encryption.outputs.key_arn
            }
          ]
        })
      }
    }
    "${local.project_name}-${local.environment}-tracking-service-irsa" = {
      permissions_boundary = "arn:aws:iam::${get_aws_account_id()}:policy/cnp-cert-app-workload-boundary"
      description          = "IRSA role for tracking-service running on EKS."
      assume_role_policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
          {
            Effect = "Allow"
            Action = "sts:AssumeRoleWithWebIdentity"
            Principal = {
              Federated = dependency.eks.outputs.oidc_provider_arn
            }
            Condition = {
              StringEquals = {
                "${replace(dependency.eks.outputs.oidc_provider_url, "https://", "")}:aud" = "sts.amazonaws.com"
                "${replace(dependency.eks.outputs.oidc_provider_url, "https://", "")}:sub" = "system:serviceaccount:${local.tracking_service_account_namespace}:${local.tracking_service_account_name}"
              }
            }
          }
        ]
      })
      inline_policies = {
        tracking-service = jsonencode({
          Version = "2012-10-17"
          Statement = [
            {
              Effect = "Allow"
              Action = [
                "events:PutEvents"
              ]
              Resource = dependency.eventbridge.outputs.event_bus_arn
            }
          ]
        })
      }
    }
  }
}
