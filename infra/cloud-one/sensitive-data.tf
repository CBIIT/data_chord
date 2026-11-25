resource "aws_macie2_account" "app" {
  count                        = var.manage_macie_account ? 1 : 0
  finding_publishing_frequency = "ONE_HOUR"
  status                       = "ENABLED"

  lifecycle {
    prevent_destroy = true
  }
}
