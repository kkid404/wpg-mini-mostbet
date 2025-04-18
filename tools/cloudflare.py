import aiohttp


CLOUDFLARE_API_BASE_URL = "https://api.cloudflare.com/client/v4"


async def get_account_id(email: str, api_key: str) -> str:
    url = f"{CLOUDFLARE_API_BASE_URL}/user"
    headers = {
        "X-Auth-Email": email,
        "X-Auth-Key": api_key,
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            data = await response.json()
            if data.get("success"):
                account_id = data["result"]["id"]
                return account_id
            else:
                raise Exception(f"Error: {data['errors']}")


async def validate_credentials(email: str, api_key: str) -> bool:
    try:
        account_id = await get_account_id(email, api_key)
        if account_id:
            print(f"Authentication successful. Account ID: {account_id}")
            return True
    except Exception as e:
        print(e)
        return False


async def delete_all_dns_records(zone_id: str, email: str, api_key: str):
    url = f"{CLOUDFLARE_API_BASE_URL}/zones/{zone_id}/dns_records"
    headers = {
        "X-Auth-Email": email,
        "X-Auth-Key": api_key,
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            data = await response.json()
            if data.get("success"):
                records = data["result"]
                for record in records:
                    record_id = record["id"]
                    delete_url = f"{url}/{record_id}"
                    async with session.delete(delete_url, headers=headers) as delete_response:
                        delete_data = await delete_response.json()
                        if delete_data.get("success"):
                            print(f"Deleted DNS record {record_id}")
                        else:
                            print(f"Failed to delete DNS record {record_id}: {delete_data['errors']}")
            else:
                print(f"Failed to list DNS records: {data['errors']}")


async def add_a_records(zone_id: str, server_ip: str, email: str, api_key: str):
    url = f"{CLOUDFLARE_API_BASE_URL}/zones/{zone_id}/dns_records"
    headers = {
        "X-Auth-Email": email,
        "X-Auth-Key": api_key,
        "Content-Type": "application/json"
    }
    records = [
        {"type": "A", "name": "@", "content": server_ip, "proxied": True},
        {"type": "A", "name": "www", "content": server_ip, "proxied": True}
    ]

    async with aiohttp.ClientSession() as session:
        for record in records:
            async with session.post(url, headers=headers, json=record) as response:
                data = await response.json()
                if data.get("success"):
                    print(f"Added DNS record: {record['name']} -> {server_ip}")
                else:
                    print(f"Failed to add DNS record: {record['name']} -> {server_ip}: {data['errors']}")


async def get_zone_id(domain: str, email: str, api_key: str) -> str:
    url = f"{CLOUDFLARE_API_BASE_URL}/zones"
    headers = {
        "X-Auth-Email": email,
        "X-Auth-Key": api_key,
        "Content-Type": "application/json"
    }
    params = {"name": domain}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            data = await response.json()
            if data.get("success") and data["result"]:
                zone_id = data["result"][0]["id"]
                return zone_id
            else:
                raise Exception(f"Error: {data['errors']}")


async def check_ns_records(zone_id: str, email: str, api_key: str):
    url = f"{CLOUDFLARE_API_BASE_URL}/zones/{zone_id}"
    headers = {
        "X-Auth-Email": email,
        "X-Auth-Key": api_key,
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            result = await response.json()
            if response.status == 200 and result["success"]:
                current_ns = result["result"]["name_servers"]
                expected_ns = result["result"]["original_name_servers"]

                print(f"Cloudflare NS records: {current_ns}")
                print(f"Expected NS records: {expected_ns}")

                return sorted(current_ns) == sorted(expected_ns)
            else:
                print(f"Failed to check NS records: {result['errors']}")
                return False


async def check_zone_status(zone_id: str, email: str, api_key: str):
    url = f"{CLOUDFLARE_API_BASE_URL}/zones/{zone_id}"
    headers = {
        "X-Auth-Email": email,
        "X-Auth-Key": api_key,
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            result = await response.json()
            if response.status == 200 and result["success"]:
                status = result["result"]["status"]
                print(f"Cloudflare Zone Status: {status}")
                return status == "active"
            else:
                print(f"Failed to check zone status: {result['errors']}")
                return False


async def get_ns_records(zone_id: str, email: str, api_key: str):
    url = f"{CLOUDFLARE_API_BASE_URL}/zones/{zone_id}"
    headers = {
        "X-Auth-Email": email,
        "X-Auth-Key": api_key,
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            result = await response.json()
            if response.status == 200 and result["success"]:
                expected_ns = result["result"]["original_name_servers"]
                return expected_ns
            else:
                print(f"Failed to check NS records: {result['errors']}")
                return None


async def add_domain_cf(domain: str, email: str, api_key: str):
    url = f"{CLOUDFLARE_API_BASE_URL}/zones"
    headers = {
        "X-Auth-Email": email,
        "X-Auth-Key": api_key,
        "Content-Type": "application/json"
    }

    data = {
        "name": domain,
        "jump_start": True
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            result = await response.json()
            try:
                if result["success"]:
                    ns_records = result["result"]["name_servers"]
                    return ns_records
                else:
                    print(f"Failed to add domain: {result['errors']}")
                    return None
            except:
                return None


async def set_ssl_full(zone_id, email, api_token):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/settings/ssl"
    headers = {
        "X-Auth-Email": email,
        "X-Auth-Key": api_token,
        "Content-Type": "application/json"
    }
    data = {
        "value": "full"
    }

    async with aiohttp.ClientSession() as session:
        async with session.patch(url, headers=headers, json=data) as response:
            result = await response.json()
            try:
                if result["success"]:
                    return True
                else:
                    return None
            except:
                return None


async def set_ssl_flex(zone_id, email, api_token):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/settings/ssl"
    headers = {
        "X-Auth-Email": email,
        "X-Auth-Key": api_token,
        "Content-Type": "application/json"
    }
    data = {
        "value": "flexible"
    }

    async with aiohttp.ClientSession() as session:
        async with session.patch(url, headers=headers, json=data) as response:
            result = await response.json()
            try:
                if result["success"]:
                    return True
                else:
                    return None
            except:
                return None



async def get_certificate_id(domain: str, zone_id: str, email: str, api_token: str):
    async with aiohttp.ClientSession() as session:
        url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/custom_certificates"
        headers = {
            "X-Auth-Email": email,
            "X-Auth-Key": api_token,
            "Content-Type": "application/json"
        }

        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                certificates = data["result"]
                if certificates:
                    for cert in certificates:
                        # Проверяем, соответствует ли сертификат домену
                        if domain in cert['hosts']:
                            print(f"Found certificate for domain: {domain}")
                            print(f"Certificate ID: {cert['id']}, Issuer: {cert['issuer']}")
                            return cert["id"]
                    raise Exception(f"No certificate found for domain {domain}.")
                else:
                    raise Exception("No certificates found for this zone.")
            else:
                error_message = await response.text()
                raise Exception(f"Error fetching certificates: {response.status} \n{error_message}")


async def get_ssl_certificate(zone_id: str, certificate_id: str, email: str, api_token: str):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/custom_certificates/{certificate_id}"

    headers = {
        "X-Auth-Email": email,
        "X-Auth-Key": api_token,
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                certificate = data["result"]["certificate"]
                private_key = data["result"]["private_key"]
                return certificate, private_key
            else:
                error_message = await response.text()
                raise Exception(f"Error fetching certificate: {response.status} \n{error_message}")