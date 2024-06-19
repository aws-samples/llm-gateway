# LLM Gateway Deployment. 

The project comprises of the following  main components.
* LLM gateway: Handles model interaction from clients. 
* Lambda Functions 
  * Api Key Handler: Manages api key for each users
  * Quota handler: Manages quota for each each users
  * Model Access Handler: Manage model access for each users
  
* Streamlit ui: Provides admin ui for the LLM gateway. 

The project needs the images to be prebuild and to be provided as input to the terraform project.


### Build Images

#### Build the api key image 

```bash
cd lambdas/api_key 
sh build_and_deploy.sh <ecr_repo_name>
```

#### Build the quota image

```bash
cd lambdas/quota 
sh build_and_deploy.sh <ecr_repo_name>
```

#### Build the model_access image

```bash
cd lambdas/model_access 
sh build_and_deploy.sh <ecr_repo_name>
```


#### Build the gateway image

```bash
cd lambdas/gateway 
sh build_and_deploy.sh <ecr_repo_name> false
```

#### Build the streamlit image

```bash
cd streamlit 
sh build_and_deploy.sh <ecr_repo_name>
```


### Deploy Terraform project 

To deploy the terraform project follow the steps. 

* Copy the example.tfvars to terraform.tfvars 
* Fill the values 
* terraform init 
* terraform plan 
* terraform apply 
* 
