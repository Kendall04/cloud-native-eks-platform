using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace ShipmentService.Infrastructure.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class OrderedTrackingInbox : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<long>(
                name: "LastProcessedTrackingSequence",
                table: "Shipments",
                type: "bigint",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Outcome",
                table: "ProcessedEvents",
                type: "character varying(64)",
                maxLength: 64,
                nullable: true);

            migrationBuilder.AddColumn<long>(
                name: "SequenceNumber",
                table: "ProcessedEvents",
                type: "bigint",
                nullable: true);

            migrationBuilder.AddColumn<Guid>(
                name: "ShipmentId",
                table: "ProcessedEvents",
                type: "uuid",
                nullable: true);

            migrationBuilder.CreateIndex(
                name: "IX_ProcessedEvents_ShipmentId_SequenceNumber",
                table: "ProcessedEvents",
                columns: new[] { "ShipmentId", "SequenceNumber" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_ProcessedEvents_ShipmentId_SequenceNumber",
                table: "ProcessedEvents");

            migrationBuilder.DropColumn(
                name: "LastProcessedTrackingSequence",
                table: "Shipments");

            migrationBuilder.DropColumn(
                name: "Outcome",
                table: "ProcessedEvents");

            migrationBuilder.DropColumn(
                name: "SequenceNumber",
                table: "ProcessedEvents");

            migrationBuilder.DropColumn(
                name: "ShipmentId",
                table: "ProcessedEvents");
        }
    }
}
