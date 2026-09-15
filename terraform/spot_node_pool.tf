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
  name                = *******************e
  resource_group_name = **********************e
}

resource "azurerm_kubernetes_cluster_node_pool" "spot" {
  name                  = *********"
  kubernetes_cluster_id = ******************************************d
  vm_size               = ****************"
  priority              = *****"
  eviction_policy       = *******"
  spot_max_price        = ****************************************************************e
  node_count            = 1
  min_count             = 0
  max_count             = 3
  auto_scaling_enabled  = ***e

  node_labels = {
    "kubernetes.azure.com/scalesetpriority" = *****"
  }
  node_taints = [
    ******************************************************"
  ]

  tags = {
    project     = **********t
    environment = **************t
    workload    = **************"
  }
}
