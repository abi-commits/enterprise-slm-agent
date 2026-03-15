{{/*
##########################################################################
# athena — Template Helpers
##########################################################################
*/}}

{{/*
Expand the chart name.
*/}}
{{- define "athena.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a fully-qualified app name. Truncated to 63 characters.
*/}}
{{- define "athena.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Chart label  (name-version)
*/}}
{{- define "athena.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels — applied to every resource.
*/}}
{{- define "athena.labels" -}}
helm.sh/chart: {{ include "athena.chart" . }}
app.kubernetes.io/name: {{ include "athena.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
{{- end }}

{{/*
Selector labels for a named component.
Usage: {{ include "athena.selectorLabels" (dict "name" . "component" "api") }}
*/}}
{{- define "athena.selectorLabels" -}}
app.kubernetes.io/name: {{ include "athena.name" .name }}
app.kubernetes.io/instance: {{ .name.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/*
Fully qualified image reference.
Usage: {{ include "athena.image" (dict "acr" .Values.global.acr "repo" .Values.api.image.repository "tag" .Values.global.imageTag) }}
*/}}
{{- define "athena.image" -}}
{{- if .acr -}}
{{- printf "%s/%s:%s" .acr .repo .tag -}}
{{- else -}}
{{- printf "%s:%s" .repo .tag -}}
{{- end -}}
{{- end }}

{{/*
Pod security context (PSS restricted) — override per component if needed.
*/}}
{{- define "athena.podSecurityContext" -}}
runAsNonRoot: {{ .Values.podSecurityContext.runAsNonRoot }}
runAsUser: {{ .Values.podSecurityContext.runAsUser }}
runAsGroup: {{ .Values.podSecurityContext.runAsGroup }}
fsGroup: {{ .Values.podSecurityContext.fsGroup }}
seccompProfile:
  type: {{ .Values.podSecurityContext.seccompProfile.type }}
{{- end }}

{{/*
Container security context (PSS restricted).
*/}}
{{- define "athena.containerSecurityContext" -}}
allowPrivilegeEscalation: {{ .Values.containerSecurityContext.allowPrivilegeEscalation }}
readOnlyRootFilesystem: {{ .Values.containerSecurityContext.readOnlyRootFilesystem }}
capabilities:
  drop:
{{- range .Values.containerSecurityContext.capabilities.drop }}
    - {{ . }}
{{- end }}
{{- end }}

{{/*
Topology spread constraints — spread pods across zones AND nodes.
Usage: {{ include "athena.topologySpread" (dict "component" "api") }}
*/}}
{{- define "athena.topologySpread" -}}
- maxSkew: 1
  topologyKey: topology.kubernetes.io/zone
  whenUnsatisfiable: DoNotSchedule
  labelSelector:
    matchLabels:
      app.kubernetes.io/component: {{ .component }}
- maxSkew: 1
  topologyKey: kubernetes.io/hostname
  whenUnsatisfiable: DoNotSchedule
  labelSelector:
    matchLabels:
      app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/*
App pool node selector + tolerations.
*/}}
{{- define "athena.appNodeSelector" -}}
nodeSelector:
  agentpool: apppool
{{- end }}

{{/*
GPU pool node selector + tolerations.
*/}}
{{- define "athena.gpuNodeSelector" -}}
nodeSelector:
  agentpool: gpupool
tolerations:
  - key: "nvidia.com/gpu"
    operator: "Equal"
    value: "present"
    effect: "NoSchedule"
{{- end }}

{{/*
Standard CSI secrets volume definition.
Usage: {{ include "athena.secretsVolume" (dict "secretProviderClass" "athena-api-kv-secrets" "secretName" "athena-api-secrets") }}
*/}}
{{- define "athena.secretsVolume" -}}
- name: secrets-store
  csi:
    driver: secrets-store.csi.k8s.io
    readOnly: true
    volumeAttributes:
      secretProviderClass: {{ .secretProviderClass }}
{{- end }}

{{/*
Standard /tmp emptyDir volume (required for readOnlyRootFilesystem).
*/}}
{{- define "athena.tmpVolume" -}}
- name: tmp
  emptyDir:
    sizeLimit: 256Mi
{{- end }}
