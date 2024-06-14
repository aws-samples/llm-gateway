output "llm_gateway_url" {
  value = "https://${module.llmgateway_alb.dns_name}"
}

#output "streamlit_url" {
#  value = "https://${module.streamlit_alb.dns_name}"
#}
