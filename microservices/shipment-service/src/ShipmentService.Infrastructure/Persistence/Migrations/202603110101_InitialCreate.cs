using System;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using ShipmentService.Infrastructure.Persistence;

namespace ShipmentService.Infrastructure.Persistence.Migrations;

[DbContext(typeof(ShipmentDbContext))]
[Migration("202603110101_InitialCreate")]
public sealed class InitialCreate : Migration
{
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.CreateTable(
            name: "ProcessedEvents",
            columns: table => new
            {
                EventId = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: false),
                EventType = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: false),
                ProcessedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_ProcessedEvents", x => x.EventId);
            });

        migrationBuilder.CreateTable(
            name: "Shipments",
            columns: table => new
            {
                Id = table.Column<Guid>(type: "uuid", nullable: false),
                TrackingNumber = table.Column<string>(type: "character varying(50)", maxLength: 50, nullable: false),
                CustomerId = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: false),
                Origin = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: false),
                Destination = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: false),
                Weight = table.Column<decimal>(type: "numeric(18,2)", nullable: false),
                Status = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                ReferenceNumber = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: true),
                Priority = table.Column<string>(type: "character varying(50)", maxLength: 50, nullable: true),
                LastTrackingEventAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                Version = table.Column<int>(type: "integer", nullable: false),
                CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_Shipments", x => x.Id);
            });

        migrationBuilder.CreateIndex(
            name: "IX_Shipments_CustomerId",
            table: "Shipments",
            column: "CustomerId");

        migrationBuilder.CreateIndex(
            name: "IX_Shipments_CustomerId_Status",
            table: "Shipments",
            columns: new[] { "CustomerId", "Status" });

        migrationBuilder.CreateIndex(
            name: "IX_Shipments_Status",
            table: "Shipments",
            column: "Status");

        migrationBuilder.CreateIndex(
            name: "IX_Shipments_TrackingNumber",
            table: "Shipments",
            column: "TrackingNumber",
            unique: true);
    }

    protected override void Down(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.DropTable(
            name: "ProcessedEvents");

        migrationBuilder.DropTable(
            name: "Shipments");
    }

    protected override void BuildTargetModel(ModelBuilder modelBuilder)
    {
        modelBuilder
            .HasAnnotation("ProductVersion", "8.0.0")
            .HasAnnotation("Relational:MaxIdentifierLength", 63);

        modelBuilder.Entity("ShipmentService.Domain.Entities.ProcessedEvent", b =>
        {
            b.Property<string>("EventId")
                .HasMaxLength(100)
                .HasColumnType("character varying(100)");

            b.Property<string>("EventType")
                .IsRequired()
                .HasMaxLength(100)
                .HasColumnType("character varying(100)");

            b.Property<DateTime>("ProcessedAt")
                .HasColumnType("timestamp with time zone");

            b.HasKey("EventId");

            b.ToTable("ProcessedEvents");
        });

        modelBuilder.Entity("ShipmentService.Domain.Entities.Shipment", b =>
        {
            b.Property<Guid>("Id")
                .HasColumnType("uuid");

            b.Property<DateTime>("CreatedAt")
                .HasColumnType("timestamp with time zone");

            b.Property<string>("CustomerId")
                .IsRequired()
                .HasMaxLength(100)
                .HasColumnType("character varying(100)");

            b.Property<string>("Destination")
                .IsRequired()
                .HasMaxLength(200)
                .HasColumnType("character varying(200)");

            b.Property<DateTime?>("LastTrackingEventAt")
                .HasColumnType("timestamp with time zone");

            b.Property<string>("Origin")
                .IsRequired()
                .HasMaxLength(200)
                .HasColumnType("character varying(200)");

            b.Property<string>("Priority")
                .HasMaxLength(50)
                .HasColumnType("character varying(50)");

            b.Property<string>("ReferenceNumber")
                .HasMaxLength(100)
                .HasColumnType("character varying(100)");

            b.Property<string>("Status")
                .IsRequired()
                .HasMaxLength(32)
                .HasColumnType("character varying(32)");

            b.Property<string>("TrackingNumber")
                .IsRequired()
                .HasMaxLength(50)
                .HasColumnType("character varying(50)");

            b.Property<DateTime>("UpdatedAt")
                .HasColumnType("timestamp with time zone");

            b.Property<int>("Version")
                .IsConcurrencyToken()
                .HasColumnType("integer");

            b.Property<decimal>("Weight")
                .HasColumnType("numeric(18,2)");

            b.HasKey("Id");

            b.HasIndex("CustomerId");

            b.HasIndex("CustomerId", "Status");

            b.HasIndex("Status");

            b.HasIndex("TrackingNumber")
                .IsUnique();

            b.ToTable("Shipments");
        });
    }
}
