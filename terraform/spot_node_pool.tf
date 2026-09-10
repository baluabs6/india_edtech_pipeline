# Optional: a Spot-priced node pool for non-latency-sensitive workloads
# (the nightly batch-scoring CronJob). Spot nodes can be reclaimed by Azure
# with short notice, which is fine for a job that just reruns tomorrow night
# if evicted, but NOT fine for the always-on API — that stays on the
# existing on-demand node pool.
#
# Assumes the AKS cluster itself already exists (referenced by name, not
# created here) — this project's terraform/ only manages Key Vault +
# Workload Identity, consistent with the rest of this repo.

data "azurerm_kubernetes_cluster" "existing" {
  name                = var.aks_cluster_name
  resource_group_name = var.resource_group_name
}

resource "azurerm_kubernetes_cluster_node_pool" "spot" {
  name                  = "spotpool"
  kubernetes_cluster_id = data.azurerm_kubernetes_cluster.existing.id
  vm_size               = "Standard_D2s_v5"
  priority              = "Spot"
  eviction_policy       = "Delete"
  spot_max_price        = -1 # pay up to the on-demand price, never evicted purely on price
  node_count            = 1
  min_count             = 0
  max_count             = 3
  auto_scaling_enabled  = true

  node_labels = {
    "kubernetes.azure.com/scalesetpriority" = "spot"
  }
  node_taints = [
    "kubernetes.azure.com/scalesetpriority=spot:NoSchedule"
  ]

  tags = {
    project     = var.project
    environment = var.environment
    workload    = "batch-scoring"
  }
}
