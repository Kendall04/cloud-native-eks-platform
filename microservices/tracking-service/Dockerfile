FROM mcr.microsoft.com/dotnet/sdk:10.0.403-noble@sha256:9c7b6b263d9d4c2e4718e16dae6d75cd8f4b5ccf206f1e7d48a98eb429981b03 AS build
WORKDIR /src

COPY ["Directory.Build.props", "."]
COPY ["TrackingService.sln", "."]
COPY ["src/TrackingService.Api/TrackingService.Api.csproj", "src/TrackingService.Api/"]
COPY ["src/TrackingService.Api/packages.lock.json", "src/TrackingService.Api/"]
COPY ["src/TrackingService.Application/TrackingService.Application.csproj", "src/TrackingService.Application/"]
COPY ["src/TrackingService.Application/packages.lock.json", "src/TrackingService.Application/"]
COPY ["src/TrackingService.Domain/TrackingService.Domain.csproj", "src/TrackingService.Domain/"]
COPY ["src/TrackingService.Domain/packages.lock.json", "src/TrackingService.Domain/"]
COPY ["src/TrackingService.Infrastructure/TrackingService.Infrastructure.csproj", "src/TrackingService.Infrastructure/"]
COPY ["src/TrackingService.Infrastructure/packages.lock.json", "src/TrackingService.Infrastructure/"]
COPY ["tests/TrackingService.Tests/TrackingService.Tests.csproj", "tests/TrackingService.Tests/"]
COPY ["tests/TrackingService.Tests/packages.lock.json", "tests/TrackingService.Tests/"]

RUN dotnet restore --locked-mode "TrackingService.sln"

COPY . .

ARG SOURCE_COMMIT=unversioned
RUN dotnet publish "src/TrackingService.Api/TrackingService.Api.csproj" \
    --configuration Release \
    --no-restore \
    --output /app/publish \
    /p:UseAppHost=false \
    /p:SourceRevisionId=${SOURCE_COMMIT}

FROM mcr.microsoft.com/dotnet/aspnet:10.0.14-noble-chiseled-extra@sha256:1b996b356531e88e7731ba694bc0ec13e2f05d25cf833e772363db84e75e467f AS final
WORKDIR /app

ENV ASPNETCORE_URLS=http://+:8080
EXPOSE 8080

COPY --from=build --chown=app:app /app/publish .

USER $APP_UID

ENTRYPOINT ["dotnet", "TrackingService.Api.dll"]
