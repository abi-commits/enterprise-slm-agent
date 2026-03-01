##########################################################################
# Module: networking
#
# Creates all network-layer resources shared by every other module:
#   - Virtual Network
#   - Node, pod, private-endpoint, and PostgreSQL-delegated subnets
#   - NSGs with explicit allow/deny rules
#   - Private DNS zones + VNet links for all PaaS services
#
# Outputs are the only coupling surface — no module reads VNet resources
# directly; they must consume this module's outputs.
##########################################################################

# ---------------------------------------------------------------------------
# Virtual Network
# ---------------------------------------------------------------------------
resource "azurerm_virtual_network" "this" {
  name                = "vnet-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = var.vnet_address_space
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# Subnets
# ---------------------------------------------------------------------------
resource "azurerm_subnet" "aks_nodes" {
  name                 = "snet-aks-nodes"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [var.aks_nodes_subnet_cidr]

  # Private endpoint network policies must be disabled on any subnet
  # hosting a private endpoint or acting as source to one.
  private_endpoint_network_policies_enabled = false
}

resource "azurerm_subnet" "aks_pods" {
  name                 = "snet-aks-pods"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [var.aks_pods_subnet_cidr]

  delegation {
    name = "aks-pod-delegation"
    service_delegation {
      name    = "Microsoft.ContainerService/managedClusters"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "private_endpoints" {
  name                 = "snet-private-endpoints"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [var.private_endpoints_subnet_cidr]

  private_endpoint_network_policies_enabled = false
}

# PostgreSQL Flexible Server requires its own dedicated delegated subnet.
resource "azurerm_subnet" "postgres_delegated" {
  name                 = "snet-postgres-delegated"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [var.postgres_delegated_subnet_cidr]

  service_endpoints = ["Microsoft.Storage"]

  delegation {
    name = "postgres-delegation"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

# ---------------------------------------------------------------------------
# Network Security Groups
# ---------------------------------------------------------------------------

# AKS node NSG: allow Azure LB + intra-VNet; deny all other inbound.
resource "azurerm_network_security_group" "aks_nodes" {
  name                = "nsg-aks-nodes-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  security_rule {
    name                       = "Allow_AzureLB_Inbound"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "AzureLoadBalancer"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Allow_VNet_Inbound"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "VirtualNetwork"
  }

  security_rule {
    name                       = "Deny_All_Inbound"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "aks_nodes" {
  subnet_id                 = azurerm_subnet.aks_nodes.id
  network_security_group_id = azurerm_network_security_group.aks_nodes.id
}

# Private-endpoints NSG: allow only AKS-sourced traffic on specific service ports.
resource "azurerm_network_security_group" "private_endpoints" {
  name                = "nsg-private-endpoints-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  security_rule {
    name                    = "Allow_AKS_Nodes_To_Services"
    priority                = 100
    direction               = "Inbound"
    access                  = "Allow"
    protocol                = "Tcp"
    source_port_range       = "*"
    destination_port_ranges = ["443", "5432", "6380"] # Key Vault HTTPS, Postgres, Redis TLS
    source_address_prefix   = var.aks_nodes_subnet_cidr
    destination_address_prefix = "*"
  }

  security_rule {
    name                    = "Allow_AKS_Pods_To_Services"
    priority                = 110
    direction               = "Inbound"
    access                  = "Allow"
    protocol                = "Tcp"
    source_port_range       = "*"
    destination_port_ranges = ["443", "5432", "6380"]
    source_address_prefix   = var.aks_pods_subnet_cidr
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Deny_All_Inbound"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "private_endpoints" {
  subnet_id                 = azurerm_subnet.private_endpoints.id
  network_security_group_id = azurerm_network_security_group.private_endpoints.id
}

# ---------------------------------------------------------------------------
# Private DNS Zones
# Each zone is linked to the VNet so private endpoints resolve correctly
# without requiring custom DNS servers.
# ---------------------------------------------------------------------------
locals {
  private_dns_zones = {
    postgres  = "privatelink.postgres.database.azure.com"
    redis     = "privatelink.redis.cache.windows.net"
    keyvault  = "privatelink.vaultcore.azure.net"
    acr       = "privatelink.azurecr.io"
  }
}

resource "azurerm_private_dns_zone" "this" {
  for_each = local.private_dns_zones

  name                = each.value
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "this" {
  for_each = local.private_dns_zones

  name                  = "pdnslink-${each.key}-${var.name_prefix}"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.this[each.key].name
  virtual_network_id    = azurerm_virtual_network.this.id
  registration_enabled  = false
  tags                  = var.tags
}
