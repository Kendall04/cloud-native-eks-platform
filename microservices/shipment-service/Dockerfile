FROM mcr.microsoft.com/dotnet/sdk:10.0.402-noble@sha256:3a48280a9a7c6276c3eeaba1efa6a08820f18c84fb9e6274c187719ecfaf9fbc AS build
WORKDIR /src

COPY ["Directory.Build.props", "."]
COPY ["ShipmentService.sln", "."]
COPY ["src/ShipmentService.Api/ShipmentService.Api.csproj", "src/ShipmentService.Api/"]
COPY ["src/ShipmentService.Api/packages.lock.json", "src/ShipmentService.Api/"]
COPY ["src/ShipmentService.Application/ShipmentService.Application.csproj", "src/ShipmentService.Application/"]
COPY ["src/ShipmentService.Application/packages.lock.json", "src/ShipmentService.Application/"]
COPY ["src/ShipmentService.Domain/ShipmentService.Domain.csproj", "src/ShipmentService.Domain/"]
COPY ["src/ShipmentService.Domain/packages.lock.json", "src/ShipmentService.Domain/"]
COPY ["src/ShipmentService.Infrastructure/ShipmentService.Infrastructure.csproj", "src/ShipmentService.Infrastructure/"]
COPY ["src/ShipmentService.Infrastructure/packages.lock.json", "src/ShipmentService.Infrastructure/"]
COPY ["tests/ShipmentService.Tests/ShipmentService.Tests.csproj", "tests/ShipmentService.Tests/"]
COPY ["tests/ShipmentService.Tests/packages.lock.json", "tests/ShipmentService.Tests/"]

RUN dotnet restore --locked-mode "ShipmentService.sln"

COPY . .

ARG SOURCE_COMMIT=unversioned
RUN dotnet publish "src/ShipmentService.Api/ShipmentService.Api.csproj" \
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

ENTRYPOINT ["dotnet", "ShipmentService.Api.dll"]
