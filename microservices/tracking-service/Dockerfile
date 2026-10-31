FROM mcr.microsoft.com/dotnet/sdk:10.0.402-noble@sha256:3a48280a9a7c6276c3eeaba1efa6a08820f18c84fb9e6274c187719ecfaf9fbc AS build
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

FROM mcr.microsoft.com/dotnet/aspnet:10.0.13-noble-chiseled-extra@sha256:6ed4a30314e8aefd56b7e7f41d2bfdefc1a7c0f967a7543ae58ac6f389fa1a40 AS final
WORKDIR /app

ENV ASPNETCORE_URLS=http://+:8080
EXPOSE 8080

COPY --from=build --chown=app:app /app/publish .

USER $APP_UID

ENTRYPOINT ["dotnet", "TrackingService.Api.dll"]
