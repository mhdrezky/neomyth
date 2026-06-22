import { ArrowRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { NeomythModule } from "@/data/modules";
import { cn } from "@/lib/utils";

interface ModuleCardProps {
  module: NeomythModule;
}

export function ModuleCard({ module }: ModuleCardProps) {
  const Icon = module.icon;
  const isAvailable = module.status === "available";

  const content = (
    <Card
      className={cn(
        "h-full transition-all",
        module.accentClass,
        isAvailable && "hover:ring-2 hover:shadow-lg cursor-pointer",
        !isAvailable && "opacity-60",
      )}
    >
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary">
            <Icon className="h-5 w-5" aria-hidden />
          </div>
          <Badge variant={isAvailable ? "default" : "secondary"}>
            {isAvailable ? "Available" : "Coming Soon"}
          </Badge>
        </div>
        <CardTitle className="text-xl">{module.name}</CardTitle>
        <CardDescription>{module.description}</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">{module.longDescription}</p>
      </CardContent>
      {isAvailable && (
        <CardFooter>
          <span className="inline-flex items-center gap-1 text-sm font-medium text-primary">
            Open tool <ArrowRight className="h-4 w-4" aria-hidden />
          </span>
        </CardFooter>
      )}
    </Card>
  );

  if (isAvailable && module.href) {
    return (
      <a href={module.href} aria-label={`Open ${module.name}`} className="block h-full">
        {content}
      </a>
    );
  }

  return <article className="h-full">{content}</article>;
}
