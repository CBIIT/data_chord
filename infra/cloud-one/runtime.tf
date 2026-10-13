resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name_prefix}"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}

resource "aws_iam_role" "task_execution" {
  name                 = "${local.name_prefix}-task-execution"
  path                 = var.application_role_path
  permissions_boundary = var.application_role_boundary_arn

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "task" {
  name                 = "${local.name_prefix}-task"
  path                 = var.application_role_path
  permissions_boundary = var.application_role_boundary_arn

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "task_data" {
  name   = "${local.name_prefix}-data"
  role   = aws_iam_role.task.id
  policy = module.data_plane.runtime_data_policy_json
}

resource "aws_iam_role_policy" "task_bedrock" {
  name = "${local.name_prefix}-bedrock"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
        ]
        Resource = [
          "arn:${data.aws_partition.current.partition}:bedrock:*::foundation-model/openai.gpt-5.6-luna*",
          "arn:${data.aws_partition.current.partition}:bedrock:*::foundation-model/openai.gpt-5.6-sol*",
          "arn:${data.aws_partition.current.partition}:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/us.openai.gpt-5.6-luna*",
          "arn:${data.aws_partition.current.partition}:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/us.openai.gpt-5.6-sol*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["bedrock:CallWithBearerToken", "bedrock-mantle:CallWithBearerToken"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = "sts:GetServiceBearerToken"
        Resource = "*"
        Condition = {
          StringEquals = {
            "sts:AWSServiceName" = "bedrock.amazonaws.com"
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = "bedrock-mantle:CreateInference"
        Resource = "arn:${data.aws_partition.current.partition}:bedrock-mantle:${var.aws_region}:${data.aws_caller_identity.current.account_id}:project/default"
      },
      {
        Effect = "Allow"
        Action = [
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_ecs_cluster" "app" {
  name = local.name_prefix

  tags = local.common_tags
}

resource "aws_security_group" "task" {
  count = var.runtime_enabled ? 1 : 0

  name        = "${local.name_prefix}-task"
  description = "Private DataChord ECS tasks"
  vpc_id      = var.vpc_id

  dynamic "ingress" {
    for_each = var.ingress_cidr_blocks
    content {
      description = "Internal DataChord traffic"
      from_port   = 8000
      to_port     = 8000
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    description = "Outbound AWS API and package access through the VPC egress path"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_ecs_task_definition" "app" {
  count = var.runtime_enabled ? 1 : 0

  family                   = local.name_prefix
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.container_cpu
  memory                   = var.container_memory
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  dynamic "ephemeral_storage" {
    for_each = var.ephemeral_storage_gib > 20 ? [var.ephemeral_storage_gib] : []
    content {
      size_in_gib = ephemeral_storage.value
    }
  }

  container_definitions = jsonencode([{
    name      = "app"
    image     = "${aws_ecr_repository.app.repository_url}@${var.image_digest}"
    essential = true
    portMappings = [{
      name          = "http"
      containerPort = 8000
      hostPort      = 8000
      protocol      = "tcp"
      appProtocol   = "http"
    }]
    environment = [
      { name = "AWS_REGION", value = var.aws_region },
      { name = "DATA_CHORD_AGENTIC_WORKERS", value = tostring(var.agentic_workers) },
      { name = "DATA_CHORD_ASSET_VERSION", value = var.image_digest },
      { name = "DATA_CHORD_CDE_RECOMMENDATION_CACHE_TABLE", value = module.data_plane.cde_recommendation_cache_table_name },
      { name = "DATA_CHORD_HARMONIZATION_CACHE_TABLE", value = module.data_plane.harmonization_cache_table_name },
      { name = "DATA_CHORD_IDENTITY_SOURCE", value = "trusted_proxy" },
      { name = "DATA_CHORD_MAX_ACTIVE_JOBS", value = tostring(var.maximum_active_jobs) },
      { name = "DATA_CHORD_PROFILE", value = "hosted" },
      { name = "DATA_CHORD_REFERENCE_TABLE", value = module.data_plane.reference_data_table_name },
      { name = "DATA_CHORD_S3_BUCKET", value = module.data_plane.workflow_bucket_name },
      { name = "DATA_CHORD_S3_PREFIX", value = local.deployment_prefix },
      { name = "DATA_CHORD_STORAGE", value = "s3" },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "app"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()\""]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
  }])

  depends_on = [
    aws_iam_role_policy.task_data,
    aws_iam_role_policy.task_bedrock,
    aws_iam_role_policy_attachment.task_execution,
  ]

  tags = local.common_tags
}

resource "aws_ecs_service" "app" {
  count = var.runtime_enabled ? 1 : 0

  name                   = local.name_prefix
  cluster                = aws_ecs_cluster.app.id
  task_definition        = aws_ecs_task_definition.app[0].arn
  desired_count          = var.desired_count
  launch_type            = "FARGATE"
  enable_execute_command = true

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 60

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.task[0].id]
    assign_public_ip = false
  }

  tags = local.common_tags
}
