include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}
terraform {
  source = "../../../modules/event-encryption"
}
