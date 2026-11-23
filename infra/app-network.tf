data "aws_availability_zones" "available" {
  # checkov:skip=CKV_AWS_394:reason=Environment contracts do not yet carry an approved two-zone allowlist;ref=CHECKOV_IMPLEMENTATION_PLAN.md;owner=DataChord Engineering;review=2027-02-28
  state = "available"
}

locals {
  public_subnet_cidrs = {
    for index, availability_zone in slice(data.aws_availability_zones.available.names, 0, 2) :
    availability_zone => cidrsubnet("10.0.0.0/16", 8, index)
  }
  public_subnet_ids = [
    for availability_zone in sort(keys(local.public_subnet_cidrs)) :
    aws_subnet.public[availability_zone].id
  ]
}

resource "aws_vpc" "app" {
  # checkov:skip=CKV2_AWS_11:reason=The approved VPC flow-log destination and retention policy are pending NCI security direction;ref=CHECKOV_EXCEPTIONS.md;owner=DataChord Engineering;review=2027-02-28
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.common_tags, {
    Name = local.name_prefix
  })
}

resource "aws_default_security_group" "app" {
  vpc_id = aws_vpc.app.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-default-deny"
  })
}

resource "aws_internet_gateway" "app" {
  vpc_id = aws_vpc.app.id

  tags = merge(local.common_tags, {
    Name = local.name_prefix
  })
}

resource "aws_subnet" "public" {
  for_each = local.public_subnet_cidrs

  vpc_id                  = aws_vpc.app.id
  availability_zone       = each.key
  cidr_block              = each.value
  map_public_ip_on_launch = false

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-public-${each.key}"
  })
}

data "aws_route_table" "main" {
  vpc_id = aws_vpc.app.id

  filter {
    name   = "association.main"
    values = ["true"]
  }
}

resource "aws_route" "public_internet" {
  route_table_id         = data.aws_route_table.main.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.app.id
}
