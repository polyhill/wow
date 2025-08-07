# WoW Damage Analyzer

This is a web-based tool to analyze World of Warcraft combat logs from Warcraft Logs (WCL) and simulate DPS gains from various stats.

这是一个基于Web的工具，用于分析Warcraft Logs (WCL)的魔兽世界战斗日志，并模拟各种属性带来的DPS增益。

---

## Features 功能

-   Fetch and display fight data from WCL reports.
-   Analyze warrior damage breakdown.
-   Simulate and visualize DPS gains from Attack Power, Weapon Skill, Crit, and Hit.
-   Bilingual interface (English/Chinese).

-   从WCL报告中获取并显示战斗数据。
-   分析战士的伤害构成。
-   模拟并可视化攻击强度、武器技能、暴击和命中带来的DPS增益。
-   双语界面（英文/中文）。

---

## Local Setup and Execution 本地设置与运行

### Prerequisites 先决条件

-   Python 3.7+
-   pip

### Installation 安装

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/polyhill/wow_damage_analyzer.git
    cd wow_damage_analyzer
    ```

2.  **Create and activate a virtual environment (recommended):**

    *   **On macOS & Linux:**
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```

    *   **On Windows:**
        ```bash
        python -m venv venv
        .\venv\Scripts\activate
        ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

### Running the Application 运行应用

1.  **Start the Flask server:**
    ```bash
    python app.py
    ```

2.  **Open your browser and navigate to:**
    ```
    http://127.0.0.1:5000
    ```

---

## Docker Deployment Docker部署

### Prerequisites 先决条件

-   Docker installed and running.

### Building the Docker Image 构建Docker镜像

1.  **Build the image using the provided Dockerfile:**
    ```bash
    docker build -t wow-damage-analyzer .
    ```

### Running the Docker Container 运行Docker容器

1.  **Run the container, mapping port 5000 to your host:**
    ```bash
    docker run -p 5000:5000 wow-damage-analyzer
    ```

2.  **Open your browser and navigate to:**
    ```
    http://localhost:5000
    ```

---

## Kubernetes Deployment Kubernetes部署

### Prerequisites 先决条件

-   A running Kubernetes cluster (e.g., Minikube, Docker Desktop Kubernetes, or a cloud provider's cluster).
-   `kubectl` configured to interact with your cluster.
-   A Docker image of the application available in a registry accessible by your cluster (e.g., Docker Hub, GCR, ECR).

### Steps 步骤

1.  **Tag and Push the Docker Image to a Registry:**
    (Replace `your-registry` with your Docker Hub username or another registry's path)
    ```bash
    docker tag wow-damage-analyzer your-registry/wow-damage-analyzer:latest
    docker push your-registry/wow-damage-analyzer:latest
    ```

2.  **Create Kubernetes Deployment and Service Manifests:**

    Create a file named `k8s-deployment.yaml` with the following content. **Remember to replace `your-registry/wow-damage-analyzer:latest` with your actual image path.**

    ```yaml
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: wow-damage-analyzer-deployment
    spec:
      replicas: 2
      selector:
        matchLabels:
          app: wow-damage-analyzer
      template:
        metadata:
          labels:
            app: wow-damage-analyzer
        spec:
          containers:
          - name: wow-damage-analyzer
            image: your-registry/wow-damage-analyzer:latest
            ports:
            - containerPort: 5000

    ---

    apiVersion: v1
    kind: Service
    metadata:
      name: wow-damage-analyzer-service
    spec:
      selector:
        app: wow-damage-analyzer
      ports:
        - protocol: TCP
          port: 80
          targetPort: 5000
      type: LoadBalancer
    ```

3.  **Apply the Manifests to Your Cluster:**
    ```bash
    kubectl apply -f k8s-deployment.yaml
    ```

4.  **Access the Application:**

    Check the status of the service to get the external IP address:
    ```bash
    kubectl get service wow-damage-analyzer-service
    ```

    Once the `EXTERNAL-IP` is available, you can access the application in your browser at that IP address. If you are using a local cluster like Minikube, you might need to use a different command:
    ```bash
    minikube service wow-damage-analyzer-service
