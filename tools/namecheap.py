import xml.etree.ElementTree as ET
import httpx


async def check_domain_in_namecheap(domain: str, nc_username: str, nc_api_key: str) -> bool:
    url = "https://api.namecheap.com/xml.response"
    params = {
        "ApiUser": nc_username,
        "ApiKey": nc_api_key,
        "UserName": nc_username,
        "Command": "namecheap.domains.check",
        "DomainList": domain,
        "ClientIp": "185.209.21.19"
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        if response.status_code == 200:
            xml_response = ET.fromstring(response.text)
            domain_check_result = xml_response.find('.//DomainCheckResult')
            if domain_check_result is not None:
                return domain_check_result.attrib.get('Available', 'false') == 'false'
        return False


async def update_ns_records_on_namecheap(domain: str, ns1: str, ns2: str, nc_username: str, nc_api_key: str) -> bool:
    url = "https://api.namecheap.com/xml.response"
    params = {
        "ApiUser": nc_username,
        "ApiKey": nc_api_key,
        "UserName": nc_username,
        "Command": "namecheap.domains.dns.setCustom",
        "SLD": domain.split('.')[0],
        "TLD": domain.split('.')[1],
        "Nameservers": f"{ns1},{ns2}",
        "ClientIp": "185.209.21.19"
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        if response.status_code == 200:
            return True
            # xml_response = ET.fromstring(response.text)
            # is_success = xml_response.find('.//ApiResponse/CommandResponse/DomainDNSSetCustomResult')
            # return is_success is not None and is_success.attrib.get('IsSuccess', 'false') == 'true'
        return False