resource "aws_security_group" "internal_alb" {
  count = local.internal_dev_preview_active ? 1 : 0

  name        = "${local.name_prefix}-internal-alb"
  description = "Internal HTTP access to the DataChord dev preview"
  vpc_id      = var.vpc_id

  dynamic "ingress" {
    for_each = var.ingress_cidr_blocks
    content {
      description = "Approved internal dev clients"
      from_port   = 80
      to_port     = 80
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    description = "Forward requests to DataChord tasks"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_lb" "internal_dev" {
  count = local.internal_dev_preview_active ? 1 : 0

  name                       = substr("${local.name_prefix}-internal", 0, 32)
  internal                   = true
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.internal_alb[0].id]
  subnets                    = var.private_subnet_ids
  drop_invalid_header_fields = true

  tags = local.common_tags
}

resource "aws_lb_target_group" "internal_dev" {
  count = local.internal_dev_preview_active ? 1 : 0

  name        = substr("${local.name_prefix}-preview", 0, 32)
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    enabled             = true
    path                = "/healthz"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = local.common_tags
}

resource "aws_lb_listener" "internal_dev_http" {
  count = local.internal_dev_preview_active ? 1 : 0

  load_balancer_arn = aws_lb.internal_dev[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.internal_dev[0].arn
  }

  tags = local.common_tags
}
