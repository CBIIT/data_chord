output "ecr_repository_name" {
  value = aws_ecr_repository.app.name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.app.name
}

output "ecs_service_name" {
  value = var.runtime_enabled ? aws_ecs_service.app[0].name : null
}

output "task_definition_arn" {
  value = var.runtime_enabled ? aws_ecs_task_definition.app[0].arn : null
}

output "runtime_enabled" {
  value = var.runtime_enabled
}

output "internal_dev_preview_url" {
  description = "Internal HTTP URL for the no-user dev preview. Reachable only through approved private network paths."
  value       = local.internal_dev_preview_active ? "http://${aws_lb.internal_dev[0].dns_name}" : null
}

output "internal_dev_target_group_arn" {
  value = local.internal_dev_preview_active ? aws_lb_target_group.internal_dev[0].arn : null
}

output "runtime_environment" {
  value = merge({
    AWS_REGION                                = var.aws_region
    DATA_CHORD_AGENTIC_WORKERS                = tostring(var.agentic_workers)
    DATA_CHORD_CDE_RECOMMENDATION_CACHE_TABLE = module.data_plane.cde_recommendation_cache_table_name
    DATA_CHORD_HARMONIZATION_CACHE_TABLE      = module.data_plane.harmonization_cache_table_name
    DATA_CHORD_IDENTITY_SOURCE                = local.internal_dev_preview_active ? "shared" : "trusted_proxy"
    DATA_CHORD_MAX_ACTIVE_JOBS                = tostring(var.maximum_active_jobs)
    DATA_CHORD_PROFILE                        = "hosted"
    DATA_CHORD_REFERENCE_TABLE                = module.data_plane.reference_data_table_name
    DATA_CHORD_S3_BUCKET                      = module.data_plane.workflow_bucket_name
    DATA_CHORD_S3_PREFIX                      = local.deployment_prefix
    DATA_CHORD_STORAGE                        = "s3"
    }, local.internal_dev_preview_active ? {
    DEV_MODE = "true"
  } : {})
}
