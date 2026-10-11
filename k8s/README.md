# Wardrobe Kubernetes Deployment

This directory contains Kubernetes manifests for deploying Wardrobe to a Kubernetes cluster.

## Prerequisites

1. **Kubernetes Cluster** - k3s, k8s, or similar
2. **Ingress Controller** - Traefik (included in k3s) or nginx-ingress
3. **cert-manager** - For automatic TLS certificates
4. **Container Registry** - Or direct image import to nodes

## Architecture

```
                    ┌─────────────────┐
                    │     Ingress     │
                    │  (TLS/HTTPS)    │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    │
   ┌─────────┐          ┌─────────┐               │
   │Frontend │          │ Backend │               │
   │  :3000  │          │  :8000  │               │
   └─────────┘          └────┬────┘               │
                             │                    │
                   ┌─────────┼─────────┐          │
                   │         │         │          │
                   ▼         ▼         ▼          │
              ┌────────┐ ┌────────┐ ┌────────┐   │
              │Postgres│ │ Redis  │ │ Worker │◄──┘
              │ :5432  │ │ :6379  │ │  (arq) │
              └────────┘ └────────┘ └────────┘
```

## Quick Start

### 1. Create Namespace

```bash
kubectl apply -f namespace.yaml
```

### 2. Configure Secrets

Copy the template and fill in your values:

```bash
cp secrets.yaml.template secrets.yaml
# Edit secrets.yaml with your values
```

Generate secure secrets:

```bash
# PostgreSQL password
openssl rand -hex 16

# NextAuth/Backend secrets
openssl rand -hex 32
```

Apply secrets:

```bash
kubectl apply -f secrets.yaml
```

### 3. Configure Settings

Edit `configmap.yaml` with your domain and AI settings:

```yaml
data:
  APP_URL: "https://wardrobe.example.com"
  NEXTAUTH_URL: "https://wardrobe.example.com"
  AI_BASE_URL: "https://api.openai.com/v1"  # Or your Ollama/LocalAI URL
```

Apply config:

```bash
kubectl apply -f configmap.yaml
```

### 4. Deploy Infrastructure

```bash
kubectl apply -f postgres.yaml
kubectl apply -f redis.yaml

# Wait for pods to be ready
kubectl -n wardrobe get pods -w
```

### 5. Deploy Application

```bash
kubectl apply -f backend.yaml
kubectl apply -f worker.yaml
kubectl apply -f image-worker.yaml
kubectl apply -f frontend.yaml
```

### 6. Configure Ingress

Edit `ingress.yaml` with your domain:

```yaml
spec:
  tls:
    - hosts:
        - wardrobe.example.com
  rules:
    - host: wardrobe.example.com
```

Apply:

```bash
kubectl apply -f ingress.yaml
```

### 7. Run Migrations

```bash
kubectl -n wardrobe exec deployment/backend -- alembic upgrade head
```

### 8. Apply Network Policies (Optional)

```bash
kubectl apply -f network-policy.yaml
```

## Upgrading

The manifests use `:latest` images with `imagePullPolicy: IfNotPresent`, so a node keeps running the image it already has until the new one is loaded and the pods restart. Back up the database first; keep the file, since a downgrade loses data and the [identity repair SQL](../docs/sign-in-identities.md#repairing-accounts-if-the-migration-ran-while-the-old-backend-was-still-serving) needs the UTC time in the name:

```bash
kubectl -n wardrobe exec deployment/postgres -- sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > backup-$(date -u +%Y%m%dT%H%M%SZ).sql
```

Then:

```bash
# 1. Make the new images reach the nodes. With images loaded onto each node, load the new ones
#    on every node. With a registry, a re-pushed :latest is not pulled again under IfNotPresent;
#    push a new tag and point the deployments at it with `kubectl -n wardrobe set image`.
# 2. Restart the pods on the new images.
kubectl -n wardrobe rollout restart deployment/backend deployment/worker deployment/frontend
kubectl -n wardrobe rollout status deployment/backend
kubectl -n wardrobe rollout status deployment/worker
kubectl -n wardrobe rollout status deployment/frontend
# Only if image-worker is deployed (kubectl -n wardrobe get deployment image-worker):
kubectl -n wardrobe rollout restart deployment/image-worker
kubectl -n wardrobe rollout status deployment/image-worker
# 3. Check the backend pod runs the new image (compare the digest with the one you built or pushed),
#    because migrating inside an old pod finds nothing to do and still reports success.
kubectl -n wardrobe get pods -l app=backend -o jsonpath='{.items[*].status.containerStatuses[*].imageID}'
# 4. Migrate inside the new backend.
kubectl -n wardrobe exec deployment/backend -- alembic upgrade head
```

## Files

| File | Description |
|------|-------------|
| `namespace.yaml` | Namespace definition |
| `configmap.yaml` | Non-sensitive configuration |
| `secrets.yaml.template` | Template for secrets |
| `secrets.yaml` | Your secrets (DO NOT commit!) |
| `postgres.yaml` | PostgreSQL database + PVC |
| `redis.yaml` | Redis for job queue + PVC |
| `backend.yaml` | FastAPI backend + PVC |
| `worker.yaml` | arq background worker |
| `frontend.yaml` | Next.js frontend |
| `ingress.yaml` | Ingress configuration |
| `network-policy.yaml` | Network isolation rules |
| `kustomization.yaml` | Kustomize configuration |

## Configuration

### AI Service

Configure your AI endpoint in `configmap.yaml`:

```yaml
# OpenAI
AI_BASE_URL: "https://api.openai.com/v1"
# Add AI_API_KEY in secrets.yaml

# Ollama (local)
AI_BASE_URL: "http://ollama:11434/v1"

# LocalAI
AI_BASE_URL: "http://localai:8080/v1"
```

### Authentication

Wardrobe supports multiple auth providers via NextAuth:

1. **Development Mode** (default): Simple email/name login
2. **OIDC Provider**: Authentik, Keycloak, Auth0, etc.
3. **Forward-auth**: an authenticating proxy such as TinyAuth or Authelia in front of the ingress. Set `forward-auth-secret` in `secrets.yaml` and `TINYAUTH_URL` or `FORWARD_AUTH_LOGOUT_URL` in `configmap.yaml`; the proxy setup is in [docs/forward-auth.md](../docs/forward-auth.md).

Configure OIDC in `configmap.yaml` and `secrets.yaml`:

```yaml
# configmap.yaml
OIDC_ISSUER_URL: "https://auth.example.com"

# secrets.yaml
oidc-client-id: "your-client-id"
oidc-client-secret: "your-client-secret"
```

#### Private CA

If the OIDC provider's certificate comes from a private CA or is self-signed, both the backend (discovery and JWKS) and the frontend (NextAuth discovery, JWKS, token exchange and userinfo) have to trust it. TLS verification stays on; you add the CA as a trust anchor. Put the PEM in a ConfigMap, mount it into `backend.yaml` and `frontend.yaml`, and set both paths in `configmap.yaml`:

```bash
kubectl -n wardrobe create configmap wardrobe-ca --from-file=internal-ca.pem
```

```yaml
# backend.yaml and frontend.yaml, in the container
volumeMounts:
  - name: wardrobe-ca
    mountPath: /certs
    readOnly: true
# and in the pod spec
volumes:
  - name: wardrobe-ca
    configMap:
      name: wardrobe-ca

# configmap.yaml
OIDC_CA_BUNDLE: "/certs/internal-ca.pem"
NODE_EXTRA_CA_CERTS: "/certs/internal-ca.pem"
```

### Storage

The uploads PVC defaults to 10Gi. Adjust in `backend.yaml`:

```yaml
spec:
  resources:
    requests:
      storage: 50Gi  # Increase as needed
```

## Troubleshooting

### Check pod status

```bash
kubectl -n wardrobe get pods
kubectl -n wardrobe describe pod <pod-name>
```

### View logs

```bash
kubectl -n wardrobe logs deployment/backend
kubectl -n wardrobe logs deployment/frontend
kubectl -n wardrobe logs deployment/worker
```

### Database connection issues

```bash
# Check if DATABASE_URL is correct
kubectl -n wardrobe exec deployment/backend -- env | grep DATABASE

# Test postgres connection
kubectl -n wardrobe exec deployment/postgres -- psql -U wardrobe -c '\l'
```

### Certificate not issuing

```bash
kubectl -n wardrobe get certificates
kubectl -n wardrobe describe certificate <cert-name>
kubectl get challenges -A
```

## Useful Commands

```bash
# Restart deployments
kubectl -n wardrobe rollout restart deployment/backend
kubectl -n wardrobe rollout restart deployment/frontend

# Scale deployments
kubectl -n wardrobe scale deployment/backend --replicas=2

# Exec into pod
kubectl -n wardrobe exec -it deployment/backend -- bash

# Port forward for local access
kubectl -n wardrobe port-forward svc/backend 8000:8000
kubectl -n wardrobe port-forward svc/frontend 3000:3000
```
