FROM mcr.microsoft.com/dotnet/sdk:10.0.403-noble@sha256:9c7b6b263d9d4c2e4718e16dae6d75cd8f4b5ccf206f1e7d48a98eb429981b03 AS build
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

FROM mcr.microsoft.com/dotnet/aspnet:10.0.14-noble-chiseled-extra@sha256:1b996b356531e88e7731ba694bc0ec13e2f05d25cf833e772363db84e75e467f AS final
WORKDIR /app

ENV ASPNETCORE_URLS=http://+:8080
EXPOSE 8080

COPY --from=build --chown=app:app /app/publish .

USER $APP_UID

ENTRYPOINT ["dotnet", "AuthService.Api.dll"]
