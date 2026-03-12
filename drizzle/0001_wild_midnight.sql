CREATE TABLE `crisis_data` (
	`id` int AUTO_INCREMENT NOT NULL,
	`dataKey` varchar(100) NOT NULL,
	`dataValue` text NOT NULL,
	`updatedAt` timestamp NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
	`updatedBy` varchar(100) DEFAULT 'system',
	CONSTRAINT `crisis_data_id` PRIMARY KEY(`id`),
	CONSTRAINT `crisis_data_dataKey_unique` UNIQUE(`dataKey`)
);
--> statement-breakpoint
CREATE TABLE `payments` (
	`id` int AUTO_INCREMENT NOT NULL,
	`userId` int NOT NULL,
	`stripeSessionId` varchar(255),
	`stripePaymentIntent` varchar(255),
	`amountCents` int NOT NULL,
	`currency` varchar(3) DEFAULT 'usd',
	`status` enum('pending','completed','failed','refunded') NOT NULL DEFAULT 'pending',
	`product` enum('full_report','subscription') NOT NULL,
	`createdAt` timestamp NOT NULL DEFAULT (now()),
	CONSTRAINT `payments_id` PRIMARY KEY(`id`)
);
--> statement-breakpoint
CREATE TABLE `report_cache` (
	`id` int AUTO_INCREMENT NOT NULL,
	`cacheKey` varchar(64) NOT NULL,
	`content` text NOT NULL,
	`riskLevel` varchar(20),
	`createdAt` timestamp NOT NULL DEFAULT (now()),
	CONSTRAINT `report_cache_id` PRIMARY KEY(`id`),
	CONSTRAINT `report_cache_cacheKey_unique` UNIQUE(`cacheKey`)
);
--> statement-breakpoint
CREATE TABLE `report_users` (
	`id` int AUTO_INCREMENT NOT NULL,
	`email` varchar(254) NOT NULL,
	`industry` varchar(100) NOT NULL,
	`country` varchar(100) NOT NULL,
	`companySize` varchar(50) NOT NULL,
	`companyName` varchar(200),
	`source` varchar(50) DEFAULT 'direct',
	`createdAt` timestamp NOT NULL DEFAULT (now()),
	CONSTRAINT `report_users_id` PRIMARY KEY(`id`)
);
--> statement-breakpoint
CREATE TABLE `reports` (
	`id` int AUTO_INCREMENT NOT NULL,
	`userId` int NOT NULL,
	`reportType` enum('free','full') NOT NULL,
	`content` text NOT NULL,
	`promptVersion` varchar(20) DEFAULT 'v1',
	`generationTimeMs` int,
	`industry` varchar(100) NOT NULL,
	`country` varchar(100) NOT NULL,
	`companySize` varchar(50) NOT NULL,
	`riskLevel` varchar(20),
	`createdAt` timestamp NOT NULL DEFAULT (now()),
	CONSTRAINT `reports_id` PRIMARY KEY(`id`)
);
--> statement-breakpoint
CREATE TABLE `subscriptions` (
	`id` int AUTO_INCREMENT NOT NULL,
	`userId` int NOT NULL,
	`stripeSubscriptionId` varchar(255),
	`stripeCustomerId` varchar(255),
	`subscriptionStatus` enum('active','cancelled','past_due') NOT NULL DEFAULT 'active',
	`currentPeriodEnd` timestamp,
	`createdAt` timestamp NOT NULL DEFAULT (now()),
	CONSTRAINT `subscriptions_id` PRIMARY KEY(`id`)
);
