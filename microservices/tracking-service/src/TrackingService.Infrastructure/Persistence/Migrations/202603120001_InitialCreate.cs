using System;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using TrackingService.Infrastructure.Persistence;

namespace TrackingService.Infrastructure.Persistence.Migrations;

[DbContext(typeof(TrackingDbContext))]
[Migration("202603120001_InitialCreate")]
public sealed class InitialCreate : Migration
{
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.CreateTable(
            name: "TrackingEvents",
            columns: table => new
            {
                Id = table.Column<Guid>(type: "uuid", nullable: false),
                ShipmentId = table.Column<Guid>(type: "uuid", nullable: false),
                Status = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                Location = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: false),
                Notes = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: true),
                SourceType = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                OccurredAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                CreatedBy = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: true),
                SequenceNumber = table.Column<int>(type: "integer", nullable: false)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_TrackingEvents", x => x.Id);
            });

        migrationBuilder.CreateIndex(
            name: "IX_TrackingEvents_OccurredAt",
            table: "TrackingEvents",
            column: "OccurredAt");

        migrationBuilder.CreateIndex(
            name: "IX_TrackingEvents_ShipmentId",
            table: "TrackingEvents",
            column: "ShipmentId");

        migrationBuilder.CreateIndex(
            name: "IX_TrackingEvents_ShipmentId_OccurredAt",
            table: "TrackingEvents",
            columns: new[] { "ShipmentId", "OccurredAt" });

        migrationBuilder.CreateIndex(
            name: "IX_TrackingEvents_ShipmentId_SequenceNumber",
            table: "TrackingEvents",
            columns: new[] { "ShipmentId", "SequenceNumber" },
            unique: true);
    }

    protected override void Down(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.DropTable(
            name: "TrackingEvents");
    }

    protected override void BuildTargetModel(ModelBuilder modelBuilder)
    {
        modelBuilder
            .HasAnnotation("ProductVersion", "8.0.0")
            .HasAnnotation("Relational:MaxIdentifierLength", 63);

        modelBuilder.Entity("TrackingService.Domain.Entities.TrackingEvent", b =>
        {
            b.Property<Guid>("Id")
                .HasColumnType("uuid");

            b.Property<DateTime>("CreatedAt")
                .HasColumnType("timestamp with time zone");

            b.Property<string>("CreatedBy")
                .HasMaxLength(100)
                .HasColumnType("character varying(100)");

            b.Property<string>("Location")
                .IsRequired()
                .HasMaxLength(200)
                .HasColumnType("character varying(200)");

            b.Property<string>("Notes")
                .HasMaxLength(500)
                .HasColumnType("character varying(500)");

            b.Property<DateTime>("OccurredAt")
                .HasColumnType("timestamp with time zone");

            b.Property<int>("SequenceNumber")
                .HasColumnType("integer");

            b.Property<Guid>("ShipmentId")
                .HasColumnType("uuid");

            b.Property<string>("SourceType")
                .IsRequired()
                .HasMaxLength(32)
                .HasColumnType("character varying(32)");

            b.Property<string>("Status")
                .IsRequired()
                .HasMaxLength(32)
                .HasColumnType("character varying(32)");

            b.HasKey("Id");

            b.HasIndex("OccurredAt");

            b.HasIndex("ShipmentId");

            b.HasIndex("ShipmentId", "OccurredAt");

            b.HasIndex("ShipmentId", "SequenceNumber")
                .IsUnique();

            b.ToTable("TrackingEvents");
        });
    }
}
