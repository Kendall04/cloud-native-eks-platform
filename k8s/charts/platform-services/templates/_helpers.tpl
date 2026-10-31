{{- define "platform-services.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" -}}
{{- end -}}

{{- define "platform-services.imageRef" -}}
{{- $repository := required "service image.repository is required" .repository -}}
{{- if .digest -}}
{{- printf "%s@%s" $repository .digest -}}
{{- else -}}
{{- $tag := required "service image.tag is required when image.digest is not set" .tag -}}
{{- printf "%s:%s" $repository $tag -}}
{{- end -}}
{{- end -}}

{{- define "platform-services.selectorLabels" -}}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/name: {{ .service.name }}
{{- end -}}

{{- define "platform-services.labels" -}}
helm.sh/chart: {{ include "platform-services.chart" .root }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
app.kubernetes.io/part-of: logistics-platform
app.kubernetes.io/component: {{ .service.component | default "service" }}
{{ include "platform-services.selectorLabels" . }}
{{- end -}}

{{- define "platform-services.releaseAnnotations" -}}
platform.cloud-native.io/release-version: {{ default "" .root.Values.release.version | quote }}
platform.cloud-native.io/release-git-tag: {{ default "" .root.Values.release.gitTag | quote }}
platform.cloud-native.io/release-commit-sha: {{ default "" .root.Values.release.commitSha | quote }}
platform.cloud-native.io/image-repository: {{ default "" .service.image.repository | quote }}
platform.cloud-native.io/image-tag: {{ default "" .service.image.tag | quote }}
platform.cloud-native.io/image-digest: {{ default "" .service.image.digest | quote }}
{{- end -}}

{{- define "platform-services.configMapName" -}}
{{- printf "%s-config" .service.name -}}
{{- end -}}

{{- define "platform-services.envList" -}}
{{- $root := .root -}}
{{- $service := .service -}}
{{- range $name, $value := $service.env }}
- name: {{ $name }}
  value: {{ ($value | toString) | quote }}
{{- end }}
{{- range $item := $service.secretEnv }}
- name: {{ $item.name }}
  valueFrom:
    secretKeyRef:
      name: {{ $item.secretName }}
      key: {{ $item.secretKey }}
{{- end }}
{{- end -}}

{{- define "platform-services.runtimeSelectorLabels" -}}
{{ include "platform-services.selectorLabels" . }}
platform.cloud-native.io/workload: runtime
{{- end -}}

{{- define "platform-services.configData" -}}
{{- range $name, $value := .service.env }}
{{ $name }}: {{ ($value | toString) | quote }}
{{- end }}
{{- end -}}
