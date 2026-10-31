using System;
using AuthService.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Storage.ValueConversion;
using Npgsql.EntityFrameworkCore.PostgreSQL.Metadata;

namespace AuthService.Infrastructure.Persistence.Migrations;

[DbContext(typeof(AuthDbContext))]
public sealed class AuthDbContextModelSnapshot : ModelSnapshot
{
    protected override void BuildModel(ModelBuilder modelBuilder)
    {
        modelBuilder
            .HasAnnotation("ProductVersion", "8.0.0")
            .HasAnnotation("Relational:MaxIdentifierLength", 63);

        modelBuilder.Entity("AuthService.Domain.Entities.ApplicationUser", b =>
        {
            b.Property<Guid>("Id")
                .HasColumnType("uuid");

            b.Property<int>("AccessFailedCount")
                .HasColumnType("integer");

            b.Property<string>("ConcurrencyStamp")
                .IsConcurrencyToken()
                .HasColumnType("text");

            b.Property<DateTime>("CreatedAt")
                .ValueGeneratedOnAdd()
                .HasColumnType("timestamp with time zone")
                .HasDefaultValueSql("NOW()");

            b.Property<string>("Email")
                .HasMaxLength(256)
                .HasColumnType("character varying(256)");

            b.Property<bool>("EmailConfirmed")
                .HasColumnType("boolean");

            b.Property<string>("FirstName")
                .IsRequired()
                .HasMaxLength(100)
                .HasColumnType("character varying(100)");

            b.Property<bool>("IsActive")
                .ValueGeneratedOnAdd()
                .HasColumnType("boolean")
                .HasDefaultValue(true);

            b.Property<string>("LastName")
                .IsRequired()
                .HasMaxLength(100)
                .HasColumnType("character varying(100)");

            b.Property<bool>("LockoutEnabled")
                .HasColumnType("boolean");

            b.Property<DateTimeOffset?>("LockoutEnd")
                .HasColumnType("timestamp with time zone");

            b.Property<string>("NormalizedEmail")
                .HasMaxLength(256)
                .HasColumnType("character varying(256)");

            b.Property<string>("NormalizedUserName")
                .HasMaxLength(256)
                .HasColumnType("character varying(256)");

            b.Property<string>("PasswordHash")
                .HasColumnType("text");

            b.Property<string>("PhoneNumber")
                .HasColumnType("text");

            b.Property<bool>("PhoneNumberConfirmed")
                .HasColumnType("boolean");

            b.Property<string>("SecurityStamp")
                .HasColumnType("text");

            b.Property<bool>("TwoFactorEnabled")
                .HasColumnType("boolean");

            b.Property<string>("UserName")
                .HasMaxLength(256)
                .HasColumnType("character varying(256)");

            b.HasKey("Id");

            b.HasIndex("NormalizedEmail")
                .HasDatabaseName("EmailIndex");

            b.HasIndex("NormalizedUserName")
                .IsUnique()
                .HasDatabaseName("UserNameIndex")
                .HasFilter("\"NormalizedUserName\" IS NOT NULL");

            b.ToTable("AspNetUsers");
        });

        modelBuilder.Entity("AuthService.Domain.Entities.RefreshToken", b =>
        {
            b.Property<Guid>("Id")
                .HasColumnType("uuid");

            b.Property<DateTime>("CreatedAt")
                .ValueGeneratedOnAdd()
                .HasColumnType("timestamp with time zone")
                .HasDefaultValueSql("NOW()");

            b.Property<DateTime>("ExpiresAt")
                .HasColumnType("timestamp with time zone");

            b.Property<DateTime?>("RevokedAt")
                .HasColumnType("timestamp with time zone");

            b.Property<string>("Token")
                .IsRequired()
                .HasMaxLength(512)
                .HasColumnType("character varying(512)");

            b.Property<Guid>("UserId")
                .HasColumnType("uuid");

            b.HasKey("Id");

            b.HasIndex("Token")
                .IsUnique();

            b.HasIndex("UserId", "ExpiresAt");

            b.ToTable("RefreshTokens");
        });

        modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityRole<System.Guid>", b =>
        {
            b.Property<Guid>("Id")
                .HasColumnType("uuid");

            b.Property<string>("ConcurrencyStamp")
                .IsConcurrencyToken()
                .HasColumnType("text");

            b.Property<string>("Name")
                .HasMaxLength(256)
                .HasColumnType("character varying(256)");

            b.Property<string>("NormalizedName")
                .HasMaxLength(256)
                .HasColumnType("character varying(256)");

            b.HasKey("Id");

            b.HasIndex("NormalizedName")
                .IsUnique()
                .HasDatabaseName("RoleNameIndex")
                .HasFilter("\"NormalizedName\" IS NOT NULL");

            b.ToTable("AspNetRoles");
        });

        modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityRoleClaim<System.Guid>", b =>
        {
            b.Property<int>("Id")
                .ValueGeneratedOnAdd()
                .HasColumnType("integer")
                .HasAnnotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn);

            b.Property<string>("ClaimType")
                .HasColumnType("text");

            b.Property<string>("ClaimValue")
                .HasColumnType("text");

            b.Property<Guid>("RoleId")
                .HasColumnType("uuid");

            b.HasKey("Id");

            b.HasIndex("RoleId");

            b.ToTable("AspNetRoleClaims");
        });

        modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityUserClaim<System.Guid>", b =>
        {
            b.Property<int>("Id")
                .ValueGeneratedOnAdd()
                .HasColumnType("integer")
                .HasAnnotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn);

            b.Property<string>("ClaimType")
                .HasColumnType("text");

            b.Property<string>("ClaimValue")
                .HasColumnType("text");

            b.Property<Guid>("UserId")
                .HasColumnType("uuid");

            b.HasKey("Id");

            b.HasIndex("UserId");

            b.ToTable("AspNetUserClaims");
        });

        modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityUserLogin<System.Guid>", b =>
        {
            b.Property<string>("LoginProvider")
                .HasMaxLength(128)
                .HasColumnType("character varying(128)");

            b.Property<string>("ProviderKey")
                .HasMaxLength(128)
                .HasColumnType("character varying(128)");

            b.Property<string>("ProviderDisplayName")
                .HasColumnType("text");

            b.Property<Guid>("UserId")
                .HasColumnType("uuid");

            b.HasKey("LoginProvider", "ProviderKey");

            b.HasIndex("UserId");

            b.ToTable("AspNetUserLogins");
        });

        modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityUserRole<System.Guid>", b =>
        {
            b.Property<Guid>("UserId")
                .HasColumnType("uuid");

            b.Property<Guid>("RoleId")
                .HasColumnType("uuid");

            b.HasKey("UserId", "RoleId");

            b.HasIndex("RoleId");

            b.ToTable("AspNetUserRoles");
        });

        modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityUserToken<System.Guid>", b =>
        {
            b.Property<Guid>("UserId")
                .HasColumnType("uuid");

            b.Property<string>("LoginProvider")
                .HasMaxLength(128)
                .HasColumnType("character varying(128)");

            b.Property<string>("Name")
                .HasMaxLength(128)
                .HasColumnType("character varying(128)");

            b.Property<string>("Value")
                .HasColumnType("text");

            b.HasKey("UserId", "LoginProvider", "Name");

            b.ToTable("AspNetUserTokens");
        });

        modelBuilder.Entity("AuthService.Domain.Entities.RefreshToken", b =>
        {
            b.HasOne("AuthService.Domain.Entities.ApplicationUser", "User")
                .WithMany("RefreshTokens")
                .HasForeignKey("UserId")
                .OnDelete(DeleteBehavior.Cascade)
                .IsRequired();

            b.Navigation("User");
        });

        modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityRoleClaim<System.Guid>", b =>
        {
            b.HasOne("Microsoft.AspNetCore.Identity.IdentityRole<System.Guid>", null)
                .WithMany()
                .HasForeignKey("RoleId")
                .OnDelete(DeleteBehavior.Cascade)
                .IsRequired();
        });

        modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityUserClaim<System.Guid>", b =>
        {
            b.HasOne("AuthService.Domain.Entities.ApplicationUser", null)
                .WithMany()
                .HasForeignKey("UserId")
                .OnDelete(DeleteBehavior.Cascade)
                .IsRequired();
        });

        modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityUserLogin<System.Guid>", b =>
        {
            b.HasOne("AuthService.Domain.Entities.ApplicationUser", null)
                .WithMany()
                .HasForeignKey("UserId")
                .OnDelete(DeleteBehavior.Cascade)
                .IsRequired();
        });

        modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityUserRole<System.Guid>", b =>
        {
            b.HasOne("Microsoft.AspNetCore.Identity.IdentityRole<System.Guid>", null)
                .WithMany()
                .HasForeignKey("RoleId")
                .OnDelete(DeleteBehavior.Cascade)
                .IsRequired();

            b.HasOne("AuthService.Domain.Entities.ApplicationUser", null)
                .WithMany()
                .HasForeignKey("UserId")
                .OnDelete(DeleteBehavior.Cascade)
                .IsRequired();
        });

        modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityUserToken<System.Guid>", b =>
        {
            b.HasOne("AuthService.Domain.Entities.ApplicationUser", null)
                .WithMany()
                .HasForeignKey("UserId")
                .OnDelete(DeleteBehavior.Cascade)
                .IsRequired();
        });

        modelBuilder.Entity("AuthService.Domain.Entities.ApplicationUser", b =>
        {
            b.Navigation("RefreshTokens");
        });
    }
}
