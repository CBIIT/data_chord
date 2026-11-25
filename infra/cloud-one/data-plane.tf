module "data_plane" {
  source = "../modules/data-plane"

  account_id                   = data.aws_caller_identity.current.account_id
  aws_region                   = var.aws_region
  common_tags                  = local.common_tags
  deployment_prefix            = local.deployment_prefix
  macie_classification_enabled = true
  name_prefix                  = local.name_prefix
  partition                    = data.aws_partition.current.partition

  depends_on = [aws_macie2_account.app]
}
