locals {
  common_tags = merge(var.tags, { Module = "sqs" })

  dlq_queues = {
    for name, queue in var.queues : name => queue
    if queue.create_dlq
  }

  queue_names = {
    for name, queue in var.queues : name => (
      queue.fifo_queue ? "${name}.fifo" : name
    )
  }

  dlq_names = {
    for name, queue in local.dlq_queues : name => (
      queue.dlq_name != null ? queue.dlq_name : (
        queue.fifo_queue ? "${name}-dlq.fifo" : "${name}-dlq"
      )
    )
  }
}

resource "aws_sqs_queue" "dlq" {
  for_each = local.dlq_queues

  name                        = local.dlq_names[each.key]
  fifo_queue                  = each.value.fifo_queue
  content_based_deduplication = each.value.fifo_queue ? each.value.content_based_deduplication : null
  message_retention_seconds   = each.value.dlq_message_retention_seconds
  kms_master_key_id           = var.event_kms_key_arn

  tags = merge(local.common_tags, {
    Name = local.dlq_names[each.key]
    Type = "dlq"
  })
}

resource "aws_sqs_queue" "this" {
  for_each = var.queues

  name                        = local.queue_names[each.key]
  fifo_queue                  = each.value.fifo_queue
  content_based_deduplication = each.value.fifo_queue ? each.value.content_based_deduplication : null
  delay_seconds               = each.value.delay_seconds
  max_message_size            = each.value.max_message_size
  message_retention_seconds   = each.value.message_retention_seconds
  visibility_timeout_seconds  = each.value.visibility_timeout_seconds
  receive_wait_time_seconds   = each.value.receive_wait_time_seconds
  kms_master_key_id           = var.event_kms_key_arn

  redrive_policy = contains(keys(local.dlq_queues), each.key) ? jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = each.value.max_receive_count
  }) : null

  tags = merge(local.common_tags, {
    Name = local.queue_names[each.key]
    Type = "primary"
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "consumer" {
  for_each  = local.dlq_queues
  queue_url = aws_sqs_queue.dlq[each.key].url
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.this[each.key].arn]
  })
}
