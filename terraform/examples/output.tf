output "llm_gateway_url" {
  value = "https://${module.llm_gateway_alb.dns_name}"
}

#output "streamlit_url" {
#  value = "https://${module.streamlit_alb.dns_name}"
#}
