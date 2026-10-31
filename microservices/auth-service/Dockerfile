FROM mcr.microsoft.com/dotnet/sdk:10.0.402-noble@sha256:3a48280a9a7c6276c3eeaba1efa6a08820f18c84fb9e6274c187719ecfaf9fbc AS build
WORKDIR /src

COPY ["Directory.Build.props", "."]
COPY ["AuthService.sln", "."]
COPY ["src/AuthService.Api/AuthService.Api.csproj", "src/AuthService.Api/"]
COPY ["src/AuthService.Api/packages.lock.json", "src/AuthService.Api/"]
COPY ["src/AuthService.Application/AuthService.Application.csproj", "src/AuthService.Application/"]
COPY ["src/AuthService.Application/packages.lock.json", "src/AuthService.Application/"]
COPY ["src/AuthService.Domain/AuthService.Domain.csproj", "src/AuthService.Domain/"]
COPY ["src/AuthService.Domain/packages.lock.json", "src/AuthService.Domain/"]
COPY ["src/AuthService.Infrastructure/AuthService.Infrastructure.csproj", "src/AuthService.Infrastructure/"]
COPY ["src/AuthService.Infrastructure/packages.lock.json", "src/AuthService.Infrastructure/"]
COPY ["tests/AuthService.Tests/AuthService.Tests.csproj", "tests/AuthService.Tests/"]
COPY ["tests/AuthService.Tests/packages.lock.json", "tests/AuthService.Tests/"]

RUN dotnet restore --locked-mode "AuthService.sln"

COPY . .

ARG SOURCE_COMMIT=unversioned
RUN dotnet publish "src/AuthService.Api/AuthService.Api.csproj" \
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

ENTRYPOINT ["dotnet", "AuthService.Api.dll"]
