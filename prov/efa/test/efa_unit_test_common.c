#include "efa_unit_tests.h"

static
struct fi_info *efa_unit_test_alloc_hints(enum fi_ep_type ep_type)
{
	struct fi_info *hints;

	hints = calloc(sizeof(struct fi_info), 1);
	if (!hints)
		return NULL;

	hints->domain_attr = calloc(sizeof(struct fi_domain_attr), 1);
	if (!hints->domain_attr) {
		fi_freeinfo(hints);
		return NULL;
	}

	hints->fabric_attr = calloc(sizeof(struct fi_fabric_attr), 1);
	if (!hints->fabric_attr) {
		fi_freeinfo(hints);
		return NULL;
	}

	hints->ep_attr = calloc(sizeof(struct fi_ep_attr), 1);
	if (!hints->ep_attr) {
		fi_freeinfo(hints);
		return NULL;
	}

	hints->fabric_attr->prov_name = EFA_PROV_NAME;
	hints->ep_attr->type = ep_type;

	hints->domain_attr->mr_mode |= FI_MR_LOCAL | FI_MR_ALLOCATED;
	if (ep_type == FI_EP_DGRAM) {
		hints->mode |= FI_MSG_PREFIX;
	}

	return hints;
}

int efa_unit_test_resource_construct(struct efa_resource *resource, enum fi_ep_type ep_type)
{
	int ret = 0;
	struct fi_av_attr av_attr = {0};
	struct fi_cq_attr cq_attr = {0};
	struct ibv_ah ibv_ah = {0};

	resource->hints = efa_unit_test_alloc_hints(ep_type);
	if (!resource->hints)
		goto err;

	/* efadv_query_device is only called once during global initialization */
	will_return_maybe(__wrap_efadv_query_device, 0);

	ret = fi_getinfo(FI_VERSION(1, 14), NULL, NULL, 0ULL, resource->hints, &resource->info);
	if (ret)
		goto err;

	ret = fi_fabric(resource->info->fabric_attr, &resource->fabric, NULL);
	if (ret)
		goto err;

	ret = fi_domain(resource->fabric, resource->info, &resource->domain, NULL);
	if (ret)
		goto err;

	ret = fi_endpoint(resource->domain, resource->info, &resource->ep, NULL);
	if (ret)
		goto err;

	if (resource->eq_attr) {
		ret = fi_eq_open(resource->fabric, resource->eq_attr, &resource->eq, NULL);
		if (ret)
			goto err;
	}

	ret = fi_av_open(resource->domain, &av_attr, &resource->av, NULL);
	if (ret)
		goto err;

	fi_ep_bind(resource->ep, &resource->av->fid, 0);

	ret = fi_cq_open(resource->domain, &cq_attr, &resource->cq, NULL);
	if (ret)
		goto err;

	fi_ep_bind(resource->ep, &resource->cq->fid, FI_SEND | FI_RECV);

	expect_any(__wrap_ibv_create_ah, pd);
	expect_any(__wrap_ibv_create_ah, attr);
	will_return(__wrap_ibv_create_ah, &ibv_ah);
	ret = fi_enable(resource->ep);
	if (ret)
		goto err;

	assert_int_equal(ret, 0);
	return 0;
err:
	efa_unit_test_resource_destruct(resource);
	return ret;
}

/**
 * @brief Clean up test resources.
 * Note: Resources should be destroyed in order.
 * @param[in] resource	struct efa_resource to clean up.
 */
void efa_unit_test_resource_destruct(struct efa_resource *resource)
{
	if (resource->ep) {
		will_return_maybe(__wrap_ibv_destroy_ah, 0);
		assert_int_equal(fi_close(&resource->ep->fid), 0);
	}

	if (resource->eq) {
		assert_int_equal(fi_close(&resource->eq->fid), 0);
	}

	if (resource->cq) {
		assert_int_equal(fi_close(&resource->cq->fid), 0);
	}

	if (resource->av) {
		assert_int_equal(fi_close(&resource->av->fid), 0);
	}

	if (resource->domain) {
		assert_int_equal(fi_close(&resource->domain->fid), 0);
	}

	if (resource->fabric) {
		assert_int_equal(fi_close(&resource->fabric->fid), 0);
	}

	if (resource->info) {
		fi_freeinfo(resource->info);
	}
}